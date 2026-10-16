"""Replay workflow boundary failures without paid models or graph services."""
import ast
import copy
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import subprocess
import sys
from functools import wraps
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from sack.runtime_support import (
    ReplyFormatError, extract_stage_body, float32_bits, missing_insight_fields,
    normalize_review, parse_json_object, strip_stage_output, validate_eda_tool_keywords, ToolCallError,
)

ROOT = Path(__file__).parents[3]
CONFIG = json.loads((ROOT / 'sack/config.json').read_text())


def load_methods(relative, class_name, names, **extra):
    """Use actual production methods, bypassing heavyweight API constructors."""
    tree = ast.parse((ROOT / relative).read_text(encoding='utf-8-sig'))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == class_name)
    methods = [n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name in names]
    for method in methods:
        method.returns = None
        for arg in method.args.args:
            arg.annotation = None
    namespace = dict(os=os, json=json, re=re, copy=copy, sys=sys, subprocess=subprocess,
                     logger=logging.getLogger('test'), logging=logging, Path=Path,
                     extract_stage_body=extract_stage_body, strip_stage_output=strip_stage_output,
                     normalize_review=normalize_review, parse_json_object=parse_json_object,
                     ReplyFormatError=ReplyFormatError, ToolCallError=ToolCallError,
                     validate_eda_tool_keywords=validate_eda_tool_keywords,
                     SACK_PACKAGE_DIR=ROOT / 'sack', **extra)
    exec(compile(ast.fix_missing_locations(ast.Module(body=methods, type_ignores=[])),
                 relative, 'exec'), namespace)
    return {name: namespace[name] for name in names}


@pytest.mark.parametrize('phase,tool_key', [
    ('In-depth Exploratory Data Analysis', 'phase_to_ml_tools'),
    ('IEDA Insight Extraction', '_phase_to_ml_tools'),
    ('Model Building, Validation, and Prediction', 'phase_to_ml_tools'),
])
def test_assembled_stage_executes_both_bodies_with_one_wrapper(tmp_path, phase, tool_key):
    prompt = ast.parse((ROOT / 'sack/Prompts/prompt_developer.py').read_text())
    prefix = next(ast.literal_eval(n.value) for n in prompt.body if isinstance(n, ast.Assign)
                  and any(getattr(t, 'id', '') == 'PREFIX_IN_CODE_FILE' for t in n.targets))
    methods = load_methods('sack/Agents/agent_developer.py', 'Developer',
                           ['_generate_code_file', '_delete_output_in_code'], PREFIX_IN_CODE_FILE=prefix)
    developer = SimpleNamespace(_is_previous_code=lambda state: (False, '', '', ''))
    developer._delete_output_in_code = lambda state, code: methods['_delete_output_in_code'](developer, state, code)
    previous = tmp_path / 'previous'
    previous.mkdir()
    state = SimpleNamespace(phase='Data Cleaning', restore_dir=str(previous), dir_name='cleaning',
                            ml_tools=CONFIG['_phase_to_ml_tools']['Data Cleaning'])
    methods['_generate_code_file'](developer, state, '```python\nmarker = 40\n```')
    developer._is_previous_code = lambda state: (True, str(previous / 'cleaning_code.py'), '', '')
    current = tmp_path / 'current'
    current.mkdir()
    state = SimpleNamespace(phase=phase, restore_dir=str(current), dir_name='stage',
                            ml_tools=CONFIG[tool_key][phase], phase_to_ml_tools=CONFIG[tool_key],
                            get_previous_phase=lambda **kw: 'Data Cleaning')
    result_file = tmp_path / 'result.txt'
    raw = f'```python\nfrom pathlib import Path\nPath({str(result_file)!r}).write_text(str(marker + 2))\n```'
    _, _, script = methods['_generate_code_file'](developer, state, raw)
    code = Path(script).read_text()
    assert code.count('def generated_code_function():') == 1
    ast.parse(code)
    tools = tmp_path / 'sack/Tools'
    tools.mkdir(parents=True)
    for module in ('ml_tools', 'eda_tools'):
        names = set(sum((list(v) for v in CONFIG[tool_key].values()), []))
        (tools / f'{module}.py').write_text('\n'.join(f'def {n}(*args, **kwargs): pass' for n in names))
    result = subprocess.run([sys.executable, script], cwd=tmp_path, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert result_file.read_text() == '42'


@pytest.mark.parametrize('previous_score', [0, 4])
@pytest.mark.parametrize("plan_mode", ["wrapped", "direct", "invalid"])
def test_eda_planner_retry_revises_plan_using_quality_feedback(tmp_path, previous_score, plan_mode):
    prompts = {}
    for relative in ('sack/Prompts/eda_prompt/prompt_planner.py',
                     'sack/Prompts/prompt_base.py'):
        tree = ast.parse((ROOT / relative).read_text(encoding='utf-8-sig'))
        for node in tree.body:
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        prompts[target.id] = node.value.value
    config_path = tmp_path / 'config.json'
    config_path.write_text(json.dumps({'user_interaction': {'plan': 'False'}}))
    methods = load_methods('sack/Agents/eda_agent/eda_planner.py', 'EDAPlanner',
                           ['_execute'], SACK_CONFIG_PATH=str(config_path), **prompts)
    gather = load_methods('sack/Agents/agent_base.py', 'Agent',
                          ['_gather_experience_with_suggestion'], **prompts)
    calls = []
    revised = 'Call test_normality and print its result.'
    plan = {'tasks': [revised]}
    raw_plan = ('invalid JSON' if plan_mode == 'invalid' else
                json.dumps({'final_answer': plan} if plan_mode == 'wrapped' else plan))
    replies = iter(['reasoning', revised, revised, raw_plan])
    parse_calls = []
    def parse(raw):
        parse_calls.append(raw)
        return json.loads(raw)
    def generate(prompt, history, **kwargs):
        calls.append(prompt)
        return next(replies), history + [{'role': 'user', 'content': prompt}]
    planner = SimpleNamespace(role='planner', description='EDA planner',
                              llm=SimpleNamespace(generate=generate),
                              _data_preview=lambda *a, **k: 'train data',
                              _get_previous_plan_and_report=lambda s: ('background plan', 'report'),
                              _read_data=lambda *a, **k: 'features',
                              _get_tools=lambda s: ('normality tool', ['test_normality']),
                              _parse_markdown=lambda raw: raw,
                              _parse_json=parse)
    planner._gather_experience_with_suggestion = lambda s: gather['_gather_experience_with_suggestion'](planner, s)
    old = {'plan': 'old incomplete plan', 'result': 'old incomplete plan'}
    state = SimpleNamespace(phase='PEDA Insight Extraction', context='EDA',
                            restore_dir=str(tmp_path), get_state_info=lambda: 'state',
                            set_background_info=lambda value: None, generate_rules=lambda: '',
                            memory=[{'planner': old, 'reviewer': {
                                'score': {'agent planner': previous_score},
                                'suggestion': {'agent planner': 'Missing tools: test_normality'}}}, {}])
    if plan_mode == 'invalid':
        with pytest.raises(ValueError):
            methods['_execute'](planner, state, 'role prompt')
        assert parse_calls == [raw_plan]
        assert (tmp_path / 'raw_json_plan_reply.txt').read_text() == raw_plan
        assert json.loads((tmp_path / 'planner_history.json').read_text())
        assert (tmp_path / 'planner_json_parse.json').exists()
        return
    result = methods['_execute'](planner, state, 'role prompt')
    assert parse_calls == [raw_plan]
    assert result['planner']['plan'] == revised
    assert result['planner'] is not old
    assert 'Missing tools: test_normality' in calls[0]
    assert 'old incomplete plan' in calls[0]
    assert 'printed to stdout' in calls[0]
    assert 'saving results to other files' in calls[0]
    assert (tmp_path / 'markdown_plan.txt').read_text() == revised
    assert json.loads((tmp_path / 'json_plan.json').read_text()) == {'tasks': [revised]}


def test_multiline_output_removal_preserves_branch_and_data_work():
    source = ['    value = 2\n', '    if value:\n', '        print(\n',
              '            value\n', '        )\n', '    value += 3\n']
    stripped = strip_stage_output(source)
    compiled = 'def work():\n' + ''.join(stripped) + '    return value\n'
    namespace = {}
    exec(compiled, namespace)
    assert namespace['work']() == 5


@pytest.mark.parametrize('mode,key', [('GetEDAInsight', 'eda_phases'), ('DSPipeline', 'phases')])
def test_first_stage_has_no_predecessor_even_with_last_stage_artifacts(mode, key):
    methods = load_methods('sack/state.py', 'State', ['get_previous_phase'],
                           load_config=lambda path: CONFIG, CONFIG_PATH='unused')
    state = SimpleNamespace(use_mode=mode, phase=CONFIG[key][0])
    assert methods['get_previous_phase'](state) is None
    assert methods['get_previous_phase'](state, type='report') is None
    assert methods['get_previous_phase'](state, type='plan') == []


def test_failed_stage_is_preserved_in_sop():
    methods = load_methods('sack/sop.py', 'SOP', ['_update_other_state'])
    sop = SimpleNamespace(state_records=[], config={'phase_to_iterations': {'Data Preparation': 2},
                                                   'max_iterations': 3})
    state = SimpleNamespace(phase='Data Preparation', score=0)
    assert methods['_update_other_state'](sop, state) == ('Fail', state)


def test_pure_json_review_keeps_original_scores_without_model_calls(tmp_path):
    methods = load_methods('sack/Agents/agent_reviewer.py', 'Reviewer',
                           ['_parse_review_replies', '_merge_dicts'])
    def forbid_call(*args, **kwargs):
        pytest.fail('Valid JSON must not call a model to reformat it')
    reviewer = SimpleNamespace(llm=SimpleNamespace(generate=forbid_call))
    state = SimpleNamespace(phase='Data Preparation', memory=[{'planner': {}, 'developer': {}}],
                            restore_dir=str(tmp_path))
    raw = [json.dumps({'final_answer': {'final_score': {f'Agent {role}': score}}})
           for role, score in [('Planner', 4), ('Developer', 5)]]
    parsed = methods['_parse_review_replies'](reviewer, raw, state)
    assert methods['_merge_dicts'](reviewer, parsed, state)['final_score'] == {
        'agent planner': 4, 'agent developer': 5}
    assert len(json.loads((tmp_path / 'reviewer_parse_attempts.json').read_text())) == 2


def test_role_scoped_reviews_ignore_conflicting_other_role_scores(tmp_path):
    methods = load_methods('sack/Agents/agent_reviewer.py', 'Reviewer',
                           ['_parse_review_replies', '_merge_dicts'])
    def forbidden(*args, **kwargs):
        pytest.fail('Valid role scores must not trigger formatting calls')
    reviewer = SimpleNamespace(llm=SimpleNamespace(generate=forbidden))
    state = SimpleNamespace(phase='IEDA Insight Extraction',
                            memory=[{'planner': {}, 'developer': {}}], restore_dir=str(tmp_path))
    raw = [json.dumps({'final_score': {'agent planner': 3, 'agent developer': 2},
                       'final_suggestion': {'agent planner': 'revise plan', 'agent developer': 'stale advice'}}),
           json.dumps({'final_score': {'agent planner': 5, 'agent developer': 4},
                       'final_suggestion': {'agent planner': 'conflicting advice', 'agent developer': 'fix code'}})]
    parsed = methods['_parse_review_replies'](reviewer, raw, state)
    merged = methods['_merge_dicts'](reviewer, parsed, state)
    assert merged == {'final_score': {'agent planner': 3, 'agent developer': 4},
                      'final_suggestion': {'agent planner': 'revise plan', 'agent developer': 'fix code'}}
    with pytest.raises(ReplyFormatError, match='Missing score'):
        normalize_review({'final_score': {'agent developer': 4}}, 'planner')


def test_invalid_review_is_reported_as_format_error_not_zero(tmp_path):
    methods = load_methods('sack/Agents/agent_reviewer.py', 'Reviewer', ['_parse_review_replies'])
    calls = []
    def invalid_reply(*args, **kwargs):
        calls.append(args)
        return '[{}]', []
    reviewer = SimpleNamespace(llm=SimpleNamespace(generate=invalid_reply))
    state = SimpleNamespace(memory=[{'developer': {}}], restore_dir=str(tmp_path))
    with pytest.raises(ReplyFormatError, match='Invalid reviewer reply'):
        methods['_parse_review_replies'](reviewer, ['[{}]'], state)
    assert len(calls) == 1
    trace = json.loads((tmp_path / 'reviewer_parse_attempts.json').read_text())
    assert len(trace) == 2 and all('error' in item for item in trace)


@pytest.mark.parametrize('raw', ['[]', '{}', '{"final_score":{"Agent Developer":true}}',
                                 '{"final_score":{"Agent Developer":9}}'])
def test_bad_review_schema_is_rejected(raw):
    with pytest.raises(ReplyFormatError):
        normalize_review(parse_json_object(raw), 'developer')


def test_json_fence_is_non_greedy_and_ambiguity_is_rejected():
    assert parse_json_object('Text\n```json\n{"a":1}\n```') == {'a': 1}
    with pytest.raises(ReplyFormatError):
        parse_json_object('```json\n{"a":1}\n```\n```json\n{"b":2}\n```')


def test_float32_encoding_accepts_numpy_scalars_and_matches_known_bits():
    assert ''.join(map(str, float32_bits(np.float32(1.0)))) == '00111111100000000000000000000000'
    assert float32_bits(np.float64(-0.0)) == [1] + [0] * 31
    assert float32_bits(np.int64(2)) == float32_bits(2.0)


def test_agent_parses_plain_json_and_markdown_without_formatting_calls():
    methods = load_methods('sack/Agents/agent_base.py', 'Agent', ['_parse_json', '_parse_markdown'])
    agent = SimpleNamespace()
    assert methods['_parse_json'](agent, '{"tool_names":["test_normality"]}') == {'tool_names': ['test_normality']}
    assert methods['_parse_markdown'](agent, '# Valid plan\nStep 1') == '# Valid plan\nStep 1'


def test_incomplete_insight_cannot_pass_stage_score():
    methods = load_methods('sack/state.py', 'State', ['set_score'])
    state = SimpleNamespace(memory=[{'reviewer': {'score': {'agent planner': 5, 'agent developer': 5}},
                                    'summarizer': {'quality_valid': False}}])
    methods['set_score'](state)
    assert state.score == 0
    assert missing_insight_fields({'a': {'b': 'unknown'}, 'c': 1}, {'a': {'b': 'unknown'}}) == ['a.b', 'c']


def test_profile_selects_train_test_and_manifest_changes_with_inputs(tmp_path):
    tree = ast.parse((ROOT / 'sack/knowledge/api/utils.py').read_text())
    functions = [n for n in tree.body if isinstance(n, ast.FunctionDef)
                 and n.name in ('_find_competition_file', '_list_competition_csv_files', 'profile_input_manifest')]
    for node in functions:
        node.returns = None
        for arg in node.args.args:
            arg.annotation = None
    namespace = {'os': os, 'hashlib': hashlib}
    exec(compile(ast.fix_missing_locations(ast.Module(body=functions, type_ignores=[])), '<profile-files>', 'exec'), namespace)
    for name in ('train.csv', 'test.csv', 'cleaned_train.csv', 'sample_submission.csv'):
        (tmp_path / name).write_text('id,value\n1,2\n')
    selected = namespace['_list_competition_csv_files'](str(tmp_path))
    assert [Path(p).name for p in selected] == ['train.csv', 'test.csv']
    before = namespace['profile_input_manifest'](str(tmp_path))
    (tmp_path / 'train.csv').write_text('id,value\n1,3\n')
    after = namespace['profile_input_manifest'](str(tmp_path))
    assert before['train.csv'] != after['train.csv']
    assert before['test.csv'] == after['test.csv']
    (tmp_path / 'overview.txt').write_text('Titanic overview')
    metadata = namespace['profile_input_manifest'](str(tmp_path))
    assert metadata['overview.txt'] == hashlib.sha256(b'Titanic overview').hexdigest()
    assert metadata['train.csv'] == after['train.csv']


@pytest.mark.parametrize('fail_column', [False, True])
def test_profile_column_failure_is_recorded_and_cannot_succeed(tmp_path, fail_column):
    tree = ast.parse((ROOT / 'sack/knowledge/api/utils.py').read_text())
    names = ('_find_competition_file', '_list_competition_csv_files', 'profile_single_competition')
    functions = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
    for node in functions:
        node.returns = None
        for arg in node.args.args:
            arg.annotation = None

    def creator(column, *args):
        if fail_column and column.name == 'Fare':
            raise ValueError('numeric fixture failure')
        return SimpleNamespace(create_profile=lambda: SimpleNamespace(
            get_embedding=lambda: [1.0] * 300, get_data_type=lambda: 'float'))

    namespace = dict(os=os, json=json, pd=pd,
        SACKKnowledgeConfig=SimpleNamespace(base_dir=str(tmp_path), data_source='kaggle'),
        fasttext=SimpleNamespace(load_model=lambda path: SimpleNamespace(
            get_sentence_vector=lambda text: np.ones(300))),
        spacy=SimpleNamespace(load=lambda name: object()),
        extract_competition_elements_local=lambda *args: {'problem_type': 'binary_classification', 'data_type': 'tabular'},
        Table=lambda **kwargs: object(),
        FineGrainedColumnTypeDetector=SimpleNamespace(detect_column_data_type=lambda *args: 'float'),
        ProfileCreator=SimpleNamespace(get_profile_creator=creator),
        generate_label=lambda label, language: SimpleNamespace(get_text=lambda: label))
    exec(compile(ast.fix_missing_locations(ast.Module(body=functions, type_ignores=[])),
                 '<actual-profile>', 'exec'), namespace)
    for name in ('train.csv', 'test.csv'):
        (tmp_path / name).write_text('Age,Fare\n22,7.25\n38,71.28\n')
    if fail_column:
        with pytest.raises(RuntimeError, match='Profile incomplete: 2 column failures'):
            namespace['profile_single_competition'](str(tmp_path))
        errors = json.loads((tmp_path / 'profile_errors.json').read_text())
        assert {e['table'] for e in errors} == {'train.csv', 'test.csv'}
        assert all(e['column'] == 'Fare' and e['error_type'] == 'ValueError' for e in errors)
    else:
        _, tables = namespace['profile_single_competition'](str(tmp_path))
        assert len(tables) == 2
        assert all(t['expected_columns'] == ['Age', 'Fare'] for t in tables)
        assert all([c['col_name'] for c in t['columns']] == ['Age', 'Fare'] for t in tables)


def test_assembled_syntax_error_is_saved_before_subprocess(tmp_path):
    def forbidden(*args, **kwargs):
        pytest.fail('Invalid assembled code must not execute')
    methods = load_methods('sack/Agents/agent_developer.py', 'Developer', ['_run_code'])
    methods['_run_code'].__globals__['subprocess'] = SimpleNamespace(run=forbidden)
    script = tmp_path / 'run.py'
    script.write_text('def generated_code_function():\n    value = )\n')
    developer = SimpleNamespace(all_error_messages=[])
    state = SimpleNamespace(restore_dir=str(tmp_path), dir_name='prepare', phase='Data Preparation')
    assert methods['_run_code'](developer, state, False, str(script)) is True
    assert 'line 2' in (tmp_path / 'prepare_error.txt').read_text()
    assert len(developer.all_error_messages) == 1


def test_caught_invalid_eda_tool_keyword_enters_debugging_before_execution(tmp_path):
    script = tmp_path / 'run.py'
    script.write_text('from Tools.eda_tools import analyze_high_cardinality_impact as impact\n'
                      'try:\n    impact(data, high_cardinality_threshold=10)\n'
                      'except Exception:\n    print("ignored")\n')
    methods = load_methods('sack/Agents/agent_developer.py', 'Developer', ['_run_code'])
    def forbidden(*args, **kwargs):
        pytest.fail('Caught invalid tool calls must be rejected before subprocess')
    methods['_run_code'].__globals__['subprocess'] = SimpleNamespace(run=forbidden)
    developer = SimpleNamespace(all_error_messages=[])
    state = SimpleNamespace(restore_dir=str(tmp_path), dir_name='deep', phase='IEDA Insight Extraction')
    assert methods['_run_code'](developer, state, False, str(script)) is True
    error = (tmp_path / 'deep_error.txt').read_text()
    assert 'high_cardinality_threshold' in error and 'Supported keywords' in error
    assert (tmp_path / 'deep_output.txt').read_text() == ''


def test_valid_eda_tool_keywords_and_other_functions_are_not_rejected():
    tools = (ROOT / 'sack/Tools/eda_tools.py').read_text()
    validate_eda_tool_keywords(
        'from Tools.eda_tools import analyze_high_cardinality_impact\n'
        'result = analyze_high_cardinality_impact(data, target_column="survived")\n'
        'unrelated(high_cardinality_threshold=10)\n', tools)


@pytest.mark.parametrize('fix_reply', ['I cannot provide corrected code.', '```python\n  \n```'])
def test_debug_reply_without_code_requests_bounded_regeneration(tmp_path, fix_reply):
    prompts = {}
    for node in ast.parse((ROOT / 'sack/Prompts/prompt_developer.py').read_text()).body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    prompts[target.id] = node.value.value
    methods = load_methods('sack/Tools/debug.py', 'DebugTool', ['debug_code_with_error'], **prompts)
    replies = iter(['locating', '```python\nwrong()\n```', fix_reply])
    calls = []
    def generate(prompt, history, **kwargs):
        calls.append(prompt)
        return next(replies), [{'role': 'assistant', 'content': calls[-1]}]
    debugger = SimpleNamespace(llm=SimpleNamespace(generate=generate))
    state = SimpleNamespace(restore_dir=str(tmp_path))
    reply, history = methods['debug_code_with_error'](
        debugger, state, ['TypeError'], '', '', 'wrong()', 'TypeError', '', [])
    assert reply == 'HELP'
    assert len(calls) == 3
    assert (tmp_path / 'debug_fix_bug.txt').read_text() == fix_reply
    assert json.loads((tmp_path / 'single_round_debug_history.json').read_text()) == history


def test_real_eda_tool_and_nested_numpy_results_are_json_serializable():
    tree = ast.parse((ROOT / 'sack/Tools/eda_tools.py').read_text())
    functions = [n for n in tree.body if isinstance(n, ast.FunctionDef)
                 and n.name in ('analyze_numerical_scale', '_native_tool_result', '_wrap_tool_result')]
    registration = tree.body[-1]
    namespace = {'__name__': 'test_eda_tools', 'np': np, 'pd': pd, '_wraps': wraps,
                 'Dict': dict, 'Any': object}
    exec(compile(ast.fix_missing_locations(ast.Module(body=functions + [registration], type_ignores=[])),
                 'actual_eda_tools', 'exec'), namespace)
    tool = namespace['analyze_numerical_scale']
    result = tool(pd.DataFrame({'value': [-2.0, 3.0]}))
    assert result['scale_classification']['unit_heterogeneity'] is True
    assert json.loads(json.dumps(result)) == result
    assert tool.__name__ == 'analyze_numerical_scale'
    assert hasattr(tool, '__wrapped__')
    nested = namespace['_native_tool_result']({'values': [np.bool_(False), np.int64(2),
                                                        np.array([1.5, 2.5])]})
    assert json.loads(json.dumps(nested)) == {'values': [False, 2, [1.5, 2.5]]}


def test_eda_summary_accepts_fenced_object_and_rejects_lists():
    methods = load_methods('sack/Agents/eda_agent/eda_summarizer.py', 'EDASummarizer',
                           ['_extract_clean_eda_insight', '_remove_evidence_fields'])
    summarizer = SimpleNamespace()
    summarizer._remove_evidence_fields = lambda data, template: methods['_remove_evidence_fields'](summarizer, data, template)
    template = {'field': 'unknown'}
    _, clean = methods['_extract_clean_eda_insight'](summarizer, '```json\n{"field":"valid"}\n```', template)
    assert clean == {'field': 'valid'}
    _, clean = methods['_extract_clean_eda_insight'](summarizer, '[{"field":"invalid"}]', template)
    assert missing_insight_fields(template, clean) == ['field']


@pytest.mark.parametrize('text,encoding', [
    ('id,name,value\n1,"Smith, Jane",7.25\n2,"Jones, Sam",8.05\n', 'utf-8'),
    ('id\tname\tvalue\n1\tJane\t7.25\n2\tSam\t8.05\n', 'utf-8'),
    ('编号,名字,金额\n1,张三,7.25\n2,李四,8.05\n', 'gb18030'),
])
def test_preparation_preview_preserves_source_separator_quotes_and_rows(tmp_path, text, encoding):
    raw = tmp_path / 'rawdata'
    raw.mkdir()
    (raw / 'train.csv').write_bytes(text.encode(encoding))
    methods = load_methods('sack/Agents/agent_base.py', 'Agent', ['_read_data'],
                           chardet=SimpleNamespace(detect=lambda data: {'encoding': encoding}), pd=pd)
    state = SimpleNamespace(phase='Data Preparation', competition_dir=str(tmp_path))
    preview = methods['_read_data'](SimpleNamespace(), state, num_lines=2)
    lines = text.splitlines(keepends=True)
    assert ''.join(lines[:2]) in preview
    assert lines[2] not in preview
    assert 'Raw CSV source preview' in preview


@pytest.mark.parametrize('degree,interaction_only,include_bias,expected_new', [
    (1, False, False, []),
    (2, False, False, ['age^2', 'age fare_log', 'fare_log^2']),
    (2, True, False, ['age fare_log']),
    (2, False, True, ['1', 'age^2', 'age fare_log', 'fare_log^2']),
])
def test_polynomial_features_keep_unique_columns_and_can_be_scaled(
        degree, interaction_only, include_bias, expected_new):
    from sklearn.preprocessing import PolynomialFeatures, StandardScaler, MinMaxScaler, RobustScaler
    from typing import Union, List
    import warnings
    tree = ast.parse((ROOT / 'sack/Tools/ml_tools.py').read_text())
    nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef)
             and n.name in ('create_polynomial_features', 'scale_features')]
    ns = dict(pd=pd, np=np, Union=Union, List=List, warnings=warnings,
              PolynomialFeatures=PolynomialFeatures, StandardScaler=StandardScaler,
              MinMaxScaler=MinMaxScaler, RobustScaler=RobustScaler)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), 'actual_ml_tools', 'exec'), ns)
    original = pd.DataFrame({'id': [1, 2, 3], 'age': [10., 20., 30.],
                             'fare_log': [1., 2., 4.]}, index=[9, 4, 7])
    result = ns['create_polynomial_features'](original, ['age', 'fare_log'], degree,
                                              interaction_only, include_bias)
    assert list(result.columns) == list(original.columns) + expected_new
    pd.testing.assert_frame_equal(result[original.columns], original)
    if 'age fare_log' in expected_new:
        np.testing.assert_array_equal(result['age fare_log'], original.age * original.fare_log)
    scaled = ns['scale_features'](result, list(result.columns[1:]), method='robust')
    assert scaled.columns.is_unique
    assert np.isfinite(scaled.to_numpy()).all()
    pd.testing.assert_frame_equal(result[original.columns], original)


@pytest.mark.parametrize('duplicate_input', [False, True])
def test_polynomial_features_reject_name_collisions_without_dropping_data(duplicate_input):
    from sklearn.preprocessing import PolynomialFeatures
    from typing import Union, List
    import warnings
    tree = ast.parse((ROOT / 'sack/Tools/ml_tools.py').read_text())
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                and n.name == 'create_polynomial_features')
    ns = dict(pd=pd, np=np, Union=Union, List=List, warnings=warnings,
              PolynomialFeatures=PolynomialFeatures)
    exec(compile(ast.Module(body=[node], type_ignores=[]), 'actual_ml_tools', 'exec'), ns)
    frame = pd.DataFrame({'age': [2., 3.], 'age^2': [99., 88.]})
    if duplicate_input:
        frame.columns = ['age', 'age']
    before = frame.copy()
    with pytest.raises(ValueError, match='duplicate column names|already exist'):
        ns['create_polynomial_features'](frame, 'age')
    pd.testing.assert_frame_equal(frame, before)


def test_eda_planner_json_example_is_valid_json():
    tree = ast.parse((ROOT / 'sack/Prompts/eda_prompt/prompt_planner.py').read_text())
    prompt = next(node.value.value for node in tree.body
                  if isinstance(node, ast.Assign)
                  and any(isinstance(target, ast.Name) and target.id == 'PROMPT_PLNNAER_REORGANIZE_IN_JSON'
                          for target in node.targets))
    sample = prompt.split('```json\n', 1)[1].split('```', 1)[0]
    value = json.loads(sample)
    assert isinstance(value['final_answer'], list)
    assert isinstance(value['final_answer'][0]['task'], str)


@pytest.mark.parametrize('case', ['constant', 'missing', 'infinite', 'valid'])
def test_conditional_dependencies_are_finite_and_use_aligned_rows(case):
    from sklearn.linear_model import LinearRegression
    from scipy import stats
    tree = ast.parse((ROOT / 'sack/Tools/eda_tools.py').read_text(encoding='utf-8-sig'))
    function = next(node for node in tree.body
                    if isinstance(node, ast.FunctionDef) and node.name == 'detect_conditional_dependencies')
    namespace = dict(pd=pd, np=np, LinearRegression=LinearRegression, stats=stats,
                     Dict=dict, Any=object)
    exec(compile(ast.fix_missing_locations(ast.Module(body=[function], type_ignores=[])),
                 'eda_tools.py', 'exec'), namespace)
    rng = np.random.default_rng(27)
    data = pd.DataFrame(rng.normal(size=(80, 3)), columns=['a', 'b', 'c'])
    if case == 'constant':
        data[:] = 1.0
    elif case == 'missing':
        for i, col in enumerate(data):
            data.loc[i * 7:i * 7 + 4, col] = np.nan
    elif case == 'infinite':
        data.loc[0, 'a'] = np.inf
        data.loc[1, 'b'] = -np.inf
    actual = namespace['detect_conditional_dependencies'](data)
    json.dumps(actual, allow_nan=False)
    strength = actual['conditional_dependency_strength']
    assert 0 <= strength <= 1
    if case == 'constant':
        assert actual == {'has_conditional_dependencies': False, 'conditional_dependency_strength': 0.0}
    else:
        clean = data.replace([np.inf, -np.inf], np.nan).dropna()
        expected = []
        for condition in clean:
            x, y = [col for col in clean if col != condition]
            residuals = [clean[col] - LinearRegression().fit(clean[[condition]], clean[col]).predict(clean[[condition]])
                         for col in (x, y)]
            expected.append(abs(stats.pearsonr(*residuals)[0]))
        assert strength == pytest.approx(round(float(np.mean(expected)), 4))


@pytest.mark.parametrize('value', [float('nan'), float('inf'), -float('inf')])
def test_insight_rejects_nonfinite_values(value):
    assert missing_insight_fields({'strength': 0.0}, {'strength': value}) == ['strength']


def test_partial_complexity_feedback_names_required_tool(tmp_path):
    validation = {'unknown_fields_count': 1,
                  'missing_schema_fields': ['complexity.dimensionality.feature_interaction_potential'],
                  'tool_output_validation': {'missing_tool_outputs': []}}
    (tmp_path / 'eda_insight_validation.json').write_text(json.dumps(validation))
    method = load_methods('sack/Agents/eda_agent/eda_summarizer.py', 'EDASummarizer', ['_execute'])['_execute']
    agent = SimpleNamespace(role='summarizer', _populate_eda_insight=lambda state: {},
                            tool_field_mapping={'deep_eda': {'assess_dataset_complexity': 'complexity'}})
    state = SimpleNamespace(phase='Deep Insight Extraction', restore_dir=tmp_path,
                            memory=[{'developer': {'status': True}, 'reviewer': {'suggestion': {}}}])
    result = method(agent, state, '')
    assert result['summarizer']['quality_valid'] is False
    for role in ('agent planner', 'agent developer'):
        assert 'assess_dataset_complexity' in state.memory[-1]['reviewer']['suggestion'][role]


@pytest.mark.parametrize('complete', [True, False])
def test_deep_complexity_helper_outputs_have_schema_mappings(complete):
    tree = ast.parse((ROOT / 'sack/Agents/eda_agent/eda_summarizer.py').read_text(encoding='utf-8-sig'))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'EDASummarizer')
    init = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == '__init__')
    assignment = next(n for n in init.body if isinstance(n, ast.Assign)
                      and any(isinstance(t, ast.Attribute) and t.attr == 'tool_field_mapping' for t in n.targets))
    mapping = ast.literal_eval(assignment.value)
    tools = ['calculate_samples_per_feature', 'estimate_feature_interaction_potential',
             'analyze_sparsity', 'estimate_signal_to_noise', 'estimate_inherent_uncertainty']
    insight = {'complexity': {'dimensionality': {'samples_per_feature': 89.1, 'feature_interaction_potential': 0.8216},
                              'sparsity_patterns': {'zero_dominated_ratio': 0.0, 'sparse_columns_ratio': 0.0},
                              'noise_level': {'signal_to_noise_estimate': 1.44, 'inherent_uncertainty': 0.9607}}}
    if not complete:
        insight['complexity']['noise_level']['inherent_uncertainty'] = 'unknown'
    methods = load_methods('sack/Agents/eda_agent/eda_summarizer.py', 'EDASummarizer',
                           ['_validate_tool_output_extraction', '_get_nested_value'])
    agent = SimpleNamespace(tool_field_mapping=mapping)
    agent._get_nested_value = lambda obj, path: methods['_get_nested_value'](agent, obj, path)
    result = methods['_validate_tool_output_extraction'](agent, insight, tools, 'deep_eda')
    assert all(result['tool_validation_details'][tool]['status'] != 'no_mapping' for tool in tools)
    assert result['missing_tool_outputs'] == ([] if complete else ['estimate_inherent_uncertainty'])
    assert mapping['pre_eda']['calculate_samples_per_feature'] == 'basic_dimensionality.samples_per_feature'


@pytest.mark.parametrize('dtype', ['Int64', 'UInt64', 'int64', 'float64'])
def test_iqr_clipping_accepts_fractional_bounds_without_losing_rows(dtype):
    from typing import Union, List
    tree = ast.parse((ROOT / 'sack/Tools/ml_tools.py').read_text())
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                and n.name == 'detect_and_handle_outliers_iqr')
    ns = dict(pd=pd, Union=Union, List=List)
    exec(compile(ast.Module(body=[node], type_ignores=[]), 'actual_ml_tools', 'exec'), ns)
    values = [0, 0, 1, 1, 100]
    if dtype in ('Int64', 'UInt64'):
        values.append(pd.NA)
    data = pd.DataFrame({'count': pd.Series(values, dtype=dtype),
                         'id': range(len(values))})
    before_ids = data.id.copy()
    result = ns['detect_and_handle_outliers_iqr'](data, 'count')
    assert result['count'].iloc[:5].tolist() == [0, 0, 1, 1, 2.5]
    pd.testing.assert_series_equal(result.id, before_ids)
    assert result['count'].isna().sum() == (1 if len(values) == 6 else 0)


def test_iqr_clipping_preserves_integer_dtype_when_no_fractional_replacement():
    from typing import Union, List
    tree = ast.parse((ROOT / 'sack/Tools/ml_tools.py').read_text())
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                and n.name == 'detect_and_handle_outliers_iqr')
    ns = dict(pd=pd, Union=Union, List=List)
    exec(compile(ast.Module(body=[node], type_ignores=[]), 'actual_ml_tools', 'exec'), ns)
    frame = pd.DataFrame({'count': pd.Series([0, 0, 1, 1, 2], dtype='Int64')})
    expected = frame.copy()
    result = ns['detect_and_handle_outliers_iqr'](frame, 'count')
    pd.testing.assert_frame_equal(result, expected)


@pytest.mark.parametrize('content,error', [
    ('', 'EmptyDataError'),
    ('id,value\n1,2\n3,4,5\n', 'ParserError'),
    (None, 'FileNotFoundError'),
])
def test_output_validation_errors_return_repair_feedback(tmp_path, content, error):
    methods = load_methods('sack/Tools/unit_test.py', 'TestTool',
                           ['execute_tests', 'test_processed_test_no_duplicated_features'], pd=pd)
    if content is not None:
        (tmp_path / 'processed_test.csv').write_text(content)
    calls = []
    tool = SimpleNamespace(
        test_processed_test_no_duplicated_features=lambda state:
            methods['test_processed_test_no_duplicated_features'](None, state),
        test_next=lambda state: (calls.append('next') or True, 99, 'healthy'),
    )
    state = SimpleNamespace(competition_dir=str(tmp_path), phase='Feature Engineering',
        phase_to_unit_tests={'Feature Engineering':
            ['test_processed_test_no_duplicated_features', 'test_next']})
    failures = methods['execute_tests'](tool, state)
    assert len(failures) == 1 and failures[0][0] is False
    assert error in failures[0][2]
    assert 'test_processed_test_no_duplicated_features' in failures[0][2]
    assert 'Repair the generated output' in failures[0][2]
    assert calls == ['next']


def test_valid_output_and_missing_document_short_circuit(tmp_path):
    methods = load_methods('sack/Tools/unit_test.py', 'TestTool',
        ['execute_tests', 'test_document_exist', 'test_processed_test_no_duplicated_features'], pd=pd)
    tool = SimpleNamespace()
    for name in methods:
        setattr(tool, name, lambda state, name=name: methods[name](tool, state))
    state = SimpleNamespace(competition_dir=str(tmp_path), phase='Feature Engineering',
        phase_to_unit_tests={'Feature Engineering':
            ['test_document_exist', 'test_processed_test_no_duplicated_features']})
    failures = tool.execute_tests(state)
    assert len(failures) == 1 and failures[0][1] == 2
    assert 'Missing files' in failures[0][2]
    for name in ['processed_train.csv', 'processed_test.csv']:
        (tmp_path / name).write_text('id,value\n1,2\n')
    assert tool.execute_tests(state) == []


def test_output_validation_does_not_swallow_keyboard_interrupt():
    methods = load_methods('sack/Tools/unit_test.py', 'TestTool', ['execute_tests'])
    def interrupted(state):
        raise KeyboardInterrupt()
    tool = SimpleNamespace(test_interrupted=interrupted)
    state = SimpleNamespace(phase='Feature Engineering',
        phase_to_unit_tests={'Feature Engineering': ['test_interrupted']})
    with pytest.raises(KeyboardInterrupt):
        methods['execute_tests'](tool, state)

@pytest.mark.parametrize('predictions', [[0, 0, 0], [1, 1, 1], [0, 1, 0]])
def test_submission_binary_labels_do_not_require_sample_distribution(tmp_path, predictions):
    import math
    method = load_methods('sack/Tools/unit_test.py', 'TestTool', ['test_submission_validity'], pd=pd, math=math)['test_submission_validity']
    pd.DataFrame({'id': [1, 2], 'Survived': [0, 1]}).to_csv(tmp_path / 'train.csv', index=False)
    pd.DataFrame({'id': [3, 4, 5], 'Survived': [0, 1, 1]}).to_csv(tmp_path / 'sample_submission.csv', index=False)
    pd.DataFrame({'id': [3, 4, 5], 'Survived': predictions}).to_csv(tmp_path / 'submission.csv', index=False)
    before = (tmp_path / 'submission.csv').read_bytes()
    assert method(None, SimpleNamespace(competition_dir=str(tmp_path)))[0] is True
    assert (tmp_path / 'submission.csv').read_bytes() == before


@pytest.mark.parametrize('case,expected', [
    ('ids', 'IDs'), ('rows', 'row count'), ('columns', 'columns'),
    ('fractional_label', 'binary class labels'), ('infinite', 'finite'), ('missing', 'missing'),
])
def test_submission_invalid_artifacts_are_rejected_without_rewriting(tmp_path, case, expected):
    import math
    method = load_methods('sack/Tools/unit_test.py', 'TestTool', ['test_submission_validity'], pd=pd, math=math)['test_submission_validity']
    pd.DataFrame({'id': [1, 2], 'Survived': [0, 1]}).to_csv(tmp_path / 'train.csv', index=False)
    sample = pd.DataFrame({'id': [3, 4], 'Survived': [0, 1]})
    sample.to_csv(tmp_path / 'sample_submission.csv', index=False)
    frame = sample.copy()
    if case == 'ids': frame['id'] = [4, 3]
    if case == 'rows': frame = frame.head(1)
    if case == 'columns': frame = frame.rename(columns={'Survived': 'wrong'})
    if case == 'fractional_label': frame['Survived'] = [0.3, 1.0]
    if case == 'infinite': frame['Survived'] = [float('inf'), 1.0]
    if case == 'missing': frame['Survived'] = [None, 1.0]
    frame.to_csv(tmp_path / 'submission.csv', index=False)
    before = (tmp_path / 'submission.csv').read_bytes()
    result = method(None, SimpleNamespace(competition_dir=str(tmp_path)))
    assert result[0] is False and expected in result[2]
    assert 'do not alter predictions' in result[2]
    assert (tmp_path / 'submission.csv').read_bytes() == before


def test_submission_regression_is_not_bounded_by_placeholder_mean(tmp_path):
    import math
    method = load_methods('sack/Tools/unit_test.py', 'TestTool', ['test_submission_validity'], pd=pd, math=math)['test_submission_validity']
    pd.DataFrame({'id': [1, 2], 'price': [20., 50.]}).to_csv(tmp_path / 'train.csv', index=False)
    pd.DataFrame({'id': [3, 4], 'price': [0., 0.]}).to_csv(tmp_path / 'sample_submission.csv', index=False)
    pd.DataFrame({'id': [3, 4], 'price': [100000., -3.]}).to_csv(tmp_path / 'submission.csv', index=False)
    assert method(None, SimpleNamespace(competition_dir=str(tmp_path)))[0] is True


@pytest.mark.parametrize('predictions,accepted', [([.2, .8], True), ([-.1, 1.1], False)])
def test_submission_binary_probability_template_uses_probability_bounds(tmp_path, predictions, accepted):
    import math
    method = load_methods('sack/Tools/unit_test.py', 'TestTool', ['test_submission_validity'], pd=pd, math=math)['test_submission_validity']
    pd.DataFrame({'id': [1, 2], 'target': [0, 1]}).to_csv(tmp_path / 'train.csv', index=False)
    pd.DataFrame({'id': [3, 4], 'target': [.5, .5]}).to_csv(tmp_path / 'sample_submission.csv', index=False)
    pd.DataFrame({'id': [3, 4], 'target': predictions}).to_csv(tmp_path / 'submission.csv', index=False)
    assert method(None, SimpleNamespace(competition_dir=str(tmp_path)))[0] is accepted


@pytest.mark.parametrize('area', ['train', 'test'])
@pytest.mark.parametrize('has_predictor', [False, True])
def test_feature_engineering_requires_real_predictors(tmp_path, area, has_predictor):
    name = f'test_processed_{area}_feature_number'
    method = load_methods('sack/Tools/unit_test.py', 'TestTool', [name], pd=pd)[name]
    pd.DataFrame({'id': [3, 4], 'Survived': [0, 1]}).to_csv(tmp_path / 'sample_submission.csv', index=False)
    original = pd.DataFrame({'id': [1, 2], 'age': [20., 30.]})
    if area == 'train': original['Survived'] = [0, 1]
    original.to_csv(tmp_path / f'cleaned_{area}.csv', index=False)
    processed = original.copy() if has_predictor else original.drop(columns='age')
    processed.to_csv(tmp_path / f'processed_{area}.csv', index=False)
    result = method(None, SimpleNamespace(competition_dir=str(tmp_path)))
    assert result[0] is has_predictor
    if not has_predictor: assert "'feature' column" in result[2]


@pytest.mark.parametrize('final_repair_valid', [False, True])
def test_developer_revalidates_last_repair_after_test_budget(tmp_path, final_repair_valid):
    prompts = {}
    for relative in ['sack/Prompts/prompt_developer.py', 'sack/Prompts/prompt_base.py']:
        for node in ast.parse((ROOT / relative).read_text(encoding='utf-8-sig')).body:
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant):
                for target in node.targets:
                    if isinstance(target, ast.Name): prompts[target.id] = node.value.value
    method = load_methods('sack/Agents/agent_developer.py', 'Developer', ['_execute'], **prompts)['_execute']
    tests, runs = [], []
    def validate(state):
        tests.append(len(runs))
        return (False, '') if len(tests) > 10 and final_repair_valid else (True, 'broken artifact')
    agent = SimpleNamespace(role='developer', description='test',
        llm=SimpleNamespace(generate=lambda *a, **kw: ('```python\npass\n```', [])),
        _generate_prompt_round1=lambda state: 'prompt',
        _generate_code_file=lambda *a: (False, '', 'script'),
        _run_code=lambda *a: (runs.append('run') or False),
        _conduct_unit_test=validate,
        _debug_code=lambda *a: ('```python\npass\n```', []))
    state = SimpleNamespace(restore_dir=str(tmp_path), competition_dir=str(tmp_path),
        dir_name='model', phase='Model Building, Validation, and Prediction', use_mode='EDAInsight',
        background_info='background', context='context', memory=[{'planner': {'plan': 'plan'}}],
        get_state_info=lambda: 'state')
    result = method(agent, state, 'role')
    assert len(tests) == 11
    assert tests[-1] == len(runs)
    assert result['developer']['status'] is final_repair_valid
