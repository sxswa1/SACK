"""Deterministic parsing and assembly at the model/runtime boundary."""
from __future__ import annotations

import ast
import json
import math
import re
import struct
import textwrap


class ReplyFormatError(ValueError):
    """A model reply is invalid; this is not a failed developer evaluation."""


class ToolCallError(ValueError):
    """Generated code calls a predefined tool with unsupported arguments."""


def validate_eda_tool_keywords(script: str, tool_source: str) -> None:
    """Check explicit keywords against source signatures without loading models."""
    tools = {node.name: node for node in ast.parse(tool_source).body
             if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
    tree = ast.parse(script)
    imported = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module in ('Tools.eda_tools', 'sack.Tools.eda_tools'):
            for alias in node.names:
                if alias.name in tools:
                    imported[alias.asname or alias.name] = alias.name
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
            continue
        name = imported.get(node.func.id)
        if name is None:
            continue
        args = tools[name].args
        if args.kwarg is not None:
            continue
        accepted = {arg.arg for arg in args.args + args.kwonlyargs}
        unsupported = [kw.arg for kw in node.keywords if kw.arg is not None and kw.arg not in accepted]
        if unsupported:
            raise ToolCallError(
                f"EDA tool {name} at line {node.lineno} does not accept keywords {unsupported}. "
                f"Supported keywords: {sorted(accepted)}. Fix the call; do not catch and skip it.")


def float32_bits(value) -> list[int]:
    """IEEE 754 big-endian float bits, including NumPy scalar inputs."""
    return [int(bit) for byte in struct.pack('>f', float(value)) for bit in f'{byte:08b}']


def missing_insight_fields(template, data, path='') -> list[str]:
    if isinstance(template, dict):
        if not isinstance(data, dict):
            return [path or '<root>']
        missing = []
        for key, expected in template.items():
            field = f'{path}.{key}' if path else key
            if key not in data:
                missing.append(field)
            else:
                missing.extend(missing_insight_fields(expected, data[key], field))
        return missing
    if (data is None or isinstance(data, str) and data.strip().lower() == 'unknown'
            or isinstance(data, float) and not math.isfinite(data)):
        return [path]
    return []


def _parse_json_value(raw: str):
    candidates = [raw.strip(), *re.findall(r"```(?:json)?\s*\n?(.*?)```", raw, re.S | re.I)]
    objects = []
    for candidate in candidates:
        try:
            value = json.loads(candidate.strip())
        except (ValueError, TypeError):
            continue
        if not any(type(value) is type(existing) and value == existing for existing in objects):
            objects.append(value)
    if len(objects) != 1:
        raise ReplyFormatError("Expected one JSON value, received invalid or ambiguous content")
    return objects[0]


def parse_json_object(raw: str) -> dict:
    value = _parse_json_value(raw)
    if not isinstance(value, dict):
        raise ReplyFormatError(f"Expected a JSON object, received {type(value).__name__}")
    return value


def parse_planner_plan(raw: str) -> dict:
    """Normalize a task array only after validating the Planner's output contract."""
    value = _parse_json_value(raw)
    if isinstance(value, list):
        value = {"final_answer": value}
    if not isinstance(value, dict) or not isinstance(value.get("final_answer"), list):
        raise ReplyFormatError('Expected a Planner object with a "final_answer" task array')
    tasks = value["final_answer"]
    if not tasks:
        raise ReplyFormatError("Planner task array must not be empty")
    fields = ("tools, involved features and correct parameters",
              "expected output or impact on data", "constraints")
    aliases = {"tools_involved_features_and_correct_parameters": fields[0],
               "expected_output_or_impact_on_data": fields[1]}
    normalized = []
    for index, task in enumerate(tasks):
        if not isinstance(task, dict) or not isinstance(task.get("task"), str) or not task["task"].strip():
            raise ReplyFormatError(f"Planner task {index} must be an object with nonempty task text")
        task = dict(task)
        for alias, field in aliases.items():
            if alias in task:
                if field in task and task[field] != task[alias]:
                    raise ReplyFormatError(f"Planner task {index}: conflicting values for {field!r}")
                task[field] = task.pop(alias)
        for field in fields:
            items = task.get(field)
            if (not isinstance(items, list) or
                    any(not isinstance(item, str) or not item.strip() for item in items) or
                    (field != "constraints" and not items)):
                raise ReplyFormatError(f"Planner task {index}: {field!r} must be a string array "
                                       "(only constraints may be empty)")
        normalized.append(task)
    return {**value, "final_answer": normalized}


def normalize_review(reply: dict, expected_role: str | None = None) -> dict:
    if not isinstance(reply, dict):
        raise ReplyFormatError("Reviewer reply must be an object")
    content = reply.get("final_answer", reply)
    if not isinstance(content, dict):
        raise ReplyFormatError("Reviewer final_answer must be an object")
    scores = content.get("final_score", content.get("score"))
    suggestions = content.get("final_suggestion", content.get("suggestion", {}))
    if not isinstance(scores, dict) or not isinstance(suggestions, dict):
        raise ReplyFormatError("Reviewer scores and suggestions must be objects")
    result = {"final_score": {}, "final_suggestion": {}, "critical_failures": []}
    for field, values in (("final_score", scores), ("final_suggestion", suggestions)):
        for key, value in values.items():
            role = re.search(r"\b(reader|planner|developer)\b", str(key).lower().replace("_", " "))
            if role is None:
                continue
            name = "agent " + role.group(1)
            # Each reviewer call evaluates one role. Other roles can leak from
            # conversation history and must not override their own evaluation.
            if expected_role and name != "agent " + expected_role:
                continue
            if field == "final_score":
                try:
                    score = float(value)
                except (TypeError, ValueError):
                    raise ReplyFormatError(f"Invalid score for {name}") from None
                if isinstance(value, bool) or not math.isfinite(score) or not 0 <= score <= 5:
                    raise ReplyFormatError(f"Invalid score for {name}")
                value = int(score) if score.is_integer() else score
            elif not isinstance(value, str):
                raise ReplyFormatError(f"Invalid suggestion for {name}")
            if name in result[field] and result[field][name] != value:
                raise ReplyFormatError(f"Conflicting {field} for {name}")
            result[field][name] = value
    if expected_role and "agent " + expected_role not in result["final_score"]:
        raise ReplyFormatError(f"Missing score for agent {expected_role}")
    if not result["final_score"]:
        raise ReplyFormatError("Reviewer reply contains no recognized scores")
    failures = content.get("critical_failures", [])
    if not isinstance(failures, list):
        raise ReplyFormatError("critical_failures must be an array")
    for failure in failures:
        if not isinstance(failure, dict):
            raise ReplyFormatError("Each critical failure must be an object")
        agent = failure.get("agent", "agent " + expected_role if expected_role else "")
        match = re.fullmatch(r"(?:agent[ _])?(reader|planner|developer)", str(agent).lower())
        if not match or any(not isinstance(failure.get(k), str) or not failure[k].strip()
                            for k in ("code", "evidence")):
            raise ReplyFormatError("Critical failures need an agent, code and concrete evidence")
        if expected_role and match[1] != expected_role:
            continue
        result["critical_failures"].append({"agent": "agent " + match[1],
                                             "code": failure["code"], "evidence": failure["evidence"]})
    return result


def extract_stage_body(source: str) -> list[str]:
    tree = ast.parse(source)
    functions = [node for node in tree.body if isinstance(node, ast.FunctionDef)
                 and node.name == "generated_code_function"]
    if len(functions) != 1:
        raise ValueError("Previous stage must contain exactly one generated_code_function")
    function = functions[0]
    lines = source.splitlines(keepends=True)
    # Includes the actual function body, independent of import/prefix length.
    start = min(getattr(node, "lineno", function.lineno) for node in function.body) - 1
    return lines[start:function.end_lineno]


def strip_stage_output(lines: list[str]) -> list[str]:
    source = textwrap.dedent("".join(lines))
    tree = ast.parse(source)

    def is_output(call):
        if not isinstance(call, ast.Call):
            return False
        func = call.func
        if isinstance(func, ast.Name):
            return func.id == "print"
        if isinstance(func, ast.Attribute):
            return (func.attr in {"plot", "hist", "show", "savefig"}
                    or isinstance(func.value, ast.Name) and func.value.id in {"plt", "sns"})
        return False

    class StripOutput(ast.NodeTransformer):
        def visit_Expr(self, node):
            return ast.copy_location(ast.Pass(), node) if is_output(node.value) else node

    tree = StripOutput().visit(tree)
    return textwrap.indent(ast.unparse(ast.fix_missing_locations(tree)), "    ").splitlines(keepends=True) + ["\n"]
