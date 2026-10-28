"""Exercise the Planner JSON boundary without API clients or model requests."""
import ast
import copy
import json
import logging
from pathlib import Path
from types import SimpleNamespace

import pytest

from sack.runtime_support import ReplyFormatError, parse_json_object, parse_planner_plan

ROOT = Path(__file__).parents[3]
TASK = {
    "task": "Inspect training feature missingness without modifying data",
    "tools, involved features and correct parameters": ["pandas.DataFrame.isna on train features"],
    "expected output or impact on data": ["Missing counts per feature"],
    "constraints": ["Preserve all source rows and identifiers"],
}


def planner_without_clients():
    # Keep the real methods and inheritance (including super), omit API imports.
    namespace = dict(Dict=dict, Any=object, parse_json_object=parse_json_object,
                     parse_planner_plan=parse_planner_plan, ReplyFormatError=ReplyFormatError,
                     logger=logging.getLogger(__name__), PROMPT_REORGANIZE_JSON="{information}")
    for name, relative in [("Agent", "sack/Agents/agent_base.py"),
                           ("Planner", "sack/Agents/agent_planner.py")]:
        tree = ast.parse((ROOT / relative).read_text(encoding="utf-8-sig"))
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == name)
        cls.body = [n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == "_parse_json"]
        exec(compile(ast.fix_missing_locations(ast.Module(body=[cls], type_ignores=[])),
                     relative, "exec"), namespace)
    planner = namespace["Planner"]()
    planner.role = "planner"
    return planner


@pytest.mark.parametrize("wrapped", [False, True])
@pytest.mark.parametrize("fenced", [False, True])
def test_valid_plan_arrays_and_objects_do_not_call_model(wrapped, fenced):
    plan = {"final_answer": [TASK]} if wrapped else [TASK]
    raw = json.dumps(plan)
    if fenced:
        raw = "```json\n" + raw + "\n```"
    planner = planner_without_clients()
    # There is intentionally no llm: normalization must not spend another call.
    assert planner._parse_json(raw) == {"final_answer": [TASK]}
    assert planner._last_json_parse["original"] == raw


@pytest.mark.parametrize("value", [[], ["text"], [{}], {"final_answer": {}},
                                  {"tasks": [TASK]}, {"final_answer": [dict(TASK, task=" ")]},
                                  None, 42])
def test_invalid_task_structures_are_rejected(value):
    with pytest.raises(ReplyFormatError):
        parse_planner_plan(json.dumps(value))


@pytest.mark.parametrize("field", list(TASK)[1:])
def test_missing_and_wrongly_typed_task_fields_are_rejected(field):
    task = copy.deepcopy(TASK)
    del task[field]
    with pytest.raises(ReplyFormatError):
        parse_planner_plan(json.dumps([task]))
    task[field] = "not an array"
    with pytest.raises(ReplyFormatError):
        parse_planner_plan(json.dumps([task]))


def test_other_agents_still_reject_arrays_and_planner_rejects_ambiguity():
    with pytest.raises(ReplyFormatError, match="object"):
        parse_json_object(json.dumps([TASK]))
    with pytest.raises(ReplyFormatError, match="ambiguous"):
        parse_planner_plan("```json\n" + json.dumps([TASK]) + "\n```\n```json\n{}\n```")
    with pytest.raises(ReplyFormatError):
        parse_planner_plan(json.dumps([TASK])[:-2])


def test_repair_field_aliases_are_normalized_without_losing_or_overriding_content():
    task = copy.deepcopy(TASK)
    task["tools_involved_features_and_correct_parameters"] = task.pop(
        "tools, involved features and correct parameters")
    task["expected_output_or_impact_on_data"] = task.pop("expected output or impact on data")
    assert parse_planner_plan(json.dumps([task])) == {"final_answer": [TASK]}
    task["tools, involved features and correct parameters"] = ["conflicting instruction"]
    with pytest.raises(ReplyFormatError, match="conflicting"):
        parse_planner_plan(json.dumps([task]))


def test_repair_receives_contract_and_retains_error_when_it_fails():
    planner = planner_without_clients()
    calls = []
    def generate(prompt, **kwargs):
        calls.append((prompt, kwargs))
        return json.dumps([TASK]), []
    planner.llm = SimpleNamespace(generate=generate)
    assert planner._parse_json('{"final_answer":') == {"final_answer": [TASK]}
    assert len(calls) == 1
    assert "Validation error:" in calls[0][0]
    assert '"final_answer"' in calls[0][0]
    assert "constraints" in calls[0][0]
    assert calls[0][1]["enable_thinking"] is False
    assert "original_error" in planner._last_json_parse
    planner.llm.generate = lambda *args, **kwargs: ('{"final_answer": []}', [])
    with pytest.raises(ReplyFormatError, match="must not be empty"):
        planner._parse_json("broken")
    assert "repair_error" in planner._last_json_parse


@pytest.mark.parametrize("relative", ["sack/Prompts/prompt_planner.py",
                                     "sack/Prompts/eda_prompt/prompt_planner.py"])
def test_prompt_examples_satisfy_the_production_contract(relative):
    tree = ast.parse((ROOT / relative).read_text(encoding="utf-8-sig"))
    prompt = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)
                  and any(getattr(t, "id", "") == "PROMPT_PLNNAER_REORGANIZE_IN_JSON" for t in n.targets))
    if "/eda_prompt/" not in relative:
        prompt = prompt.format(task_core_elements="requirements", insight_reference_spec="references")
    assert parse_planner_plan(prompt)["final_answer"]
