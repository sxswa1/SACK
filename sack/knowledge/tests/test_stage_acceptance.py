"""Regression coverage for false completion and unexecuted model predictions."""
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from sack.model_audit import validate_receipt
from sack.runtime_support import normalize_review, ReplyFormatError
from sack.knowledge.tests.test_titanic_workflow_regressions import load_methods

ROOT = Path(__file__).parents[3]


@pytest.mark.parametrize('scores,expected', [({'agent planner': 4, 'agent developer': 2}, 2),
    ({'agent planner': 2, 'agent developer': 5}, 2),
    ({'agent planner': 4, 'agent developer': 3}, 3),
    ({'agent planner': 5}, 0), ({}, 0),
    ({'agent planner': 5, 'agent developer': float('nan')}, 0)])
def test_each_required_role_must_pass(scores, expected):
    state = SimpleNamespace(phase='Feature Engineering', memory=[{
        'reviewer': {'score': scores, 'result': {'critical_failures': []}},
        'developer': {'status': True}}])
    load_methods('sack/state.py', 'State', ['set_score'])['set_score'](state)
    assert state.score == expected


def test_critical_failure_survives_parse_merge_and_blocks_high_scores():
    failure = {'agent': 'agent developer', 'code': 'FABRICATED_METRIC',
               'evidence': 'Line 10 hardcodes accuracy=0.95 without training'}
    developer = normalize_review({'final_score': {'agent developer': 5},
                                 'critical_failures': [failure]}, 'developer')
    planner = normalize_review({'final_score': {'agent planner': 5}}, 'planner')
    merge = load_methods('sack/Agents/agent_reviewer.py', 'Reviewer', ['_merge_dicts'])['_merge_dicts']
    result = merge(None, [planner, developer], SimpleNamespace(phase='Model Building, Validation, and Prediction'))
    assert result['critical_failures'] == [failure]
    assert result['final_score']['agent developer'] == 0
    assert 'FABRICATED_METRIC' in result['final_suggestion']['agent developer']
    # Even conflicting high scores elsewhere must not override the critical flag.
    state = SimpleNamespace(phase='Model Building, Validation, and Prediction', memory=[{
        'reviewer': {'score': {'agent planner': 5, 'agent developer': 5}, 'result': result},
        'developer': {'status': True, 'training_evidence': {'passed': True}}}])
    load_methods('sack/state.py', 'State', ['set_score'])['set_score'](state)
    assert state.score == 0


@pytest.mark.parametrize('evidence,status', [({}, True), ({'passed': False}, True),
                                          ({'passed': True}, False), ({'passed': True}, None)])
def test_model_completion_requires_execution_and_training(evidence, status):
    state = SimpleNamespace(phase='Model Building, Validation, and Prediction', memory=[{
        'reviewer': {'score': {'agent planner': 5, 'agent developer': 5}},
        'developer': {'status': status, 'training_evidence': evidence}}])
    load_methods('sack/state.py', 'State', ['set_score'])['set_score'](state)
    assert state.score == 0


def test_reader_has_its_own_required_score_and_failures_require_evidence():
    state = SimpleNamespace(phase='Understand Background', memory=[{'reviewer': {'score': {'agent reader': 4}}}])
    load_methods('sack/state.py', 'State', ['set_score'])['set_score'](state)
    assert state.score == 4
    with pytest.raises(ReplyFormatError, match='concrete evidence'):
        normalize_review({'final_score': {'agent developer': 5},
                          'critical_failures': [{'code': 'FABRICATED_METRIC'}]}, 'developer')


def make_task(root):
    raw = root / 'rawdata'
    raw.mkdir()
    x = np.r_[np.linspace(-2, -0.1, 30), np.linspace(0.1, 2, 30)]
    train = pd.DataFrame({'id': [f'train-{i}' for i in range(60)], 'x': x,
                          'type': ['Ghost'] * 30 + ['Ghoul'] * 30})
    test = pd.DataFrame({'id': ['001', '007'], 'x': [-1., 1.]})
    sample = pd.DataFrame({'id': test.id, 'type': ['Ghost', 'Ghost']})
    for name, frame in [('train.csv', train), ('test.csv', test), ('sample_submission.csv', sample)]:
        frame.to_csv(raw / name, index=False)
    train.to_csv(root / 'processed_train.csv', index=False)
    test.to_csv(root / 'processed_test.csv', index=False)


def execute(task, body):
    script = task / 'generated.py'
    script.write_text(body)
    env = dict(os.environ, PYTHONPATH=str(ROOT) + os.pathsep + str(ROOT / 'sack'))
    result = subprocess.run([sys.executable, '-m', 'sack.model_audit', '--script', str(script),
        '--task', str(task), '--receipt', str(task / 'training_execution.json'), '--run-id', 'this-run'],
        cwd=task, env=env, capture_output=True, text=True, timeout=60)
    return result, json.loads((task / 'training_execution.json').read_text())


TRAIN = '''
import pandas as pd
from sack.Tools.ml_tools import train_and_validation_and_select_the_best_model
train = pd.read_csv('processed_train.csv')
test = pd.read_csv('processed_test.csv')
X = train[['x']]
y = train['type'].map({'Ghost': 0, 'Ghoul': 1})
model = train_and_validation_and_select_the_best_model(X, y, problem_type='binary', selected_models=['SVM'])
predictions = model.predict(test[['x']])
labels = pd.Series(predictions).map({0: 'Ghost', 1: 'Ghoul'})
submission = pd.read_csv('rawdata/sample_submission.csv', dtype=str)
submission['type'] = labels
submission.to_csv('submission.csv', index=False)
'''


def test_real_tool_training_encoded_labels_and_seed_are_accepted(tmp_path):
    make_task(tmp_path)
    result, receipt = execute(tmp_path, 'import random\nrandom.seed(42)\n' + TRAIN)
    assert result.returncode == 0, result.stderr
    assert receipt['passed'] and receipt['training_rows'] == 60 and receipt['prediction_rows'] == 2
    assert receipt['validation_metric'] == 'accuracy'
    assert receipt['full_data_refit'] is True
    validate_receipt(tmp_path, tmp_path / 'generated.py', tmp_path / 'training_execution.json', 'this-run')
    with pytest.raises(ValueError, match='current execution'):
        validate_receipt(tmp_path, tmp_path / 'generated.py', tmp_path / 'training_execution.json', 'old-run')
    (tmp_path / 'submission.csv').write_text('id,type\n001,Ghoul\n007,Ghost\n')
    with pytest.raises(ValueError, match='Submission changed'):
        validate_receipt(tmp_path, tmp_path / 'generated.py', tmp_path / 'training_execution.json')


def test_fake_training_with_a_valid_submission_is_rejected(tmp_path):
    make_task(tmp_path)
    result, receipt = execute(tmp_path, '''
import shutil
print("Best model: XGBoost, accuracy: 0.95")
shutil.copyfile('rawdata/sample_submission.csv', 'submission.csv')
''')
    assert result.returncode != 0
    assert receipt['passed'] is False
    assert 'No verified model prediction' in receipt['error']


@pytest.mark.parametrize('change', ["submission['type'] = ['Ghost', 'Ghost']",
                                  "submission['id'] = ['007', '001']",
                                  "submission['type'] = ['GHOST', 'GHOUL']"])
def test_real_training_cannot_justify_fabricated_or_misaligned_outputs(tmp_path, change):
    make_task(tmp_path)
    result, receipt = execute(tmp_path, TRAIN + '\n' + change + "\nsubmission.to_csv('submission.csv', index=False)\n")
    assert result.returncode != 0
    assert receipt['passed'] is False


def test_a_failed_rerun_invalidates_previous_success(tmp_path):
    make_task(tmp_path)
    assert execute(tmp_path, TRAIN)[0].returncode == 0
    result, receipt = execute(tmp_path, "raise RuntimeError('failed current run')")
    assert result.returncode != 0 and receipt['passed'] is False
    assert 'failed current run' in receipt['error']


@pytest.mark.parametrize('real_training', [False, True])
def test_developer_executes_audited_runner_and_receives_real_evidence(tmp_path, monkeypatch, real_training):
    make_task(tmp_path)
    script = tmp_path / 'generated.py'
    script.write_text(TRAIN if real_training else
                      "import shutil\nshutil.copyfile('rawdata/sample_submission.csv', 'submission.csv')")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('PYTHONPATH', str(ROOT) + os.pathsep + str(ROOT / 'sack'))
    method = load_methods('sack/Agents/agent_developer.py', 'Developer', ['_run_code'],
                          uuid=uuid, validate_receipt=validate_receipt)['_run_code']
    state = SimpleNamespace(phase='Model Building, Validation, and Prediction',
                            competition_dir=str(tmp_path), restore_dir=str(tmp_path), dir_name='model_build_predict')
    developer = SimpleNamespace(all_error_messages=[], _save_all_error_messages=lambda state: None)
    error = method(developer, state, False, str(script))
    assert error is not real_training
    assert developer._training_evidence.get('passed', False) is real_training
