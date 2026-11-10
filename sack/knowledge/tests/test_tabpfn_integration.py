"""Candidate selection, limits and evidence; no weights or network needed."""
from importlib.metadata import PackageNotFoundError
import sys
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from sack import tabpfn_support as support
from sack.Tools.ml_tools import train_and_validation_and_select_the_best_model as train
from sack.model_audit import AuditSession


@pytest.fixture
def table():
    x = np.r_[np.linspace(-2, -.1, 30), np.linspace(.1, 2, 30)]
    return pd.DataFrame({'x': x}), pd.Series((x > 0).astype(int))


def fake_package(monkeypatch, tmp_path, installed='2.1.3', cuda=False):
    monkeypatch.setattr(support, 'version', lambda _: installed)
    monkeypatch.setitem(sys.modules, 'torch', SimpleNamespace(
        cuda=SimpleNamespace(is_available=lambda: cuda)))
    class Model:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)
    monkeypatch.setitem(sys.modules, 'tabpfn', SimpleNamespace(
        TabPFNClassifier=Model, TabPFNRegressor=Model))
    monkeypatch.setattr(support, 'ensure_checkpoint',
                        lambda directory, kind: directory / f'tabpfn-v2-{kind}.ckpt')
    monkeypatch.setenv('SACK_TABPFN_MODEL_DIR', str(tmp_path / 'weights'))
    monkeypatch.setenv('SACK_TABPFN_DEVICE', 'auto')
    monkeypatch.delenv('SACK_TABPFN_N_ESTIMATORS', raising=False)
    monkeypatch.delenv('SACK_TABPFN_N_JOBS', raising=False)


@pytest.mark.parametrize('problem,filename', [('binary', 'classifier'), ('regression', 'regressor')])
def test_explicit_original_checkpoint_and_reproducible_options(monkeypatch, tmp_path, table, problem, filename):
    fake_package(monkeypatch, tmp_path)
    model = support.create_tabpfn(*table, problem)
    assert model.model_path.name == f'tabpfn-v2-{filename}.ckpt'
    assert model.device == 'cpu' and model.random_state == 42
    assert model.n_jobs == 1 and model.ignore_pretraining_limits is False


@pytest.mark.parametrize('rows,cols,classes,device,message', [
    (1001, 2, 2, 'cpu', '1000 rows'),
    (10001, 2, 2, 'cuda', '10000 rows'),
    (20, 501, 2, 'cpu', '500 features'),
    (20, 2, 11, 'cpu', '10 classes'),
])
def test_limits_apply_before_fit_on_full_data(monkeypatch, tmp_path, rows, cols, classes, device, message):
    fake_package(monkeypatch, tmp_path, cuda=device == 'cuda')
    X, y = pd.DataFrame(np.zeros((rows, cols))), pd.Series(np.arange(rows) % classes)
    with pytest.raises(ValueError, match=message):
        support.create_tabpfn(X, y, 'multiclass')
    assert not (tmp_path / 'weights').exists()


def test_missing_and_wrong_package_versions_are_actionable(monkeypatch, tmp_path, table):
    def missing(_):
        raise PackageNotFoundError('tabpfn')
    monkeypatch.setattr(support, 'version', missing)
    with pytest.raises(ImportError, match='requirements-tabpfn.txt'):
        support.create_tabpfn(*table, 'binary')
    fake_package(monkeypatch, tmp_path, installed='9.2.0')
    with pytest.raises(ValueError, match='requires tabpfn==2.1.3'):
        support.create_tabpfn(*table, 'binary')


def test_unexpected_checkpoint_is_rejected_before_loading(tmp_path):
    (tmp_path / 'tabpfn-v2-classifier.ckpt').write_bytes(b'unexpected weights')
    with pytest.raises(ValueError, match='SHA-256 mismatch'):
        support.ensure_checkpoint(tmp_path, 'classifier')


@pytest.mark.parametrize('setting,value', [('SACK_TABPFN_DEVICE', 'mps'),
    ('SACK_TABPFN_DEVICE', 'cuda'), ('SACK_TABPFN_N_ESTIMATORS', '0'),
    ('SACK_TABPFN_N_JOBS', '-1')])
def test_bad_configuration_fails_clearly(monkeypatch, tmp_path, table, setting, value):
    fake_package(monkeypatch, tmp_path)
    monkeypatch.setenv(setting, value)
    with pytest.raises(ValueError):
        support.create_tabpfn(*table, 'binary')


@pytest.mark.parametrize('failure', ['unavailable', 'predict', 'refit'])
def test_optional_failure_falls_back_with_measured_evidence(monkeypatch, table, failure):
    calls = []
    class Candidate:
        n_estimators = 1
        def fit(self, X, y):
            calls.append(len(X))
            if failure == 'refit' and len(X) == 60:
                raise RuntimeError('refit out of memory')
            return self
        def predict(self, X):
            if failure == 'predict':
                raise RuntimeError('predict out of memory')
            return (X.x > 0).astype(int).to_numpy()
    def create(*args):
        if failure == 'unavailable':
            raise ImportError('not installed')
        return Candidate()
    monkeypatch.setattr(support, 'create_tabpfn', create)
    captured = {}
    def record(model, X, y, results, score, metric):
        captured.update(results=results, rows=len(X), score=score)
        return model
    monkeypatch.setattr('sack.model_audit.record_training', record)
    with pytest.warns(RuntimeWarning, match='TabPFN'):
        model = train(*table, selected_models=['TabPFN', 'SVM'])
    assert type(model).__name__ == 'SVC'
    assert captured['rows'] == 60 and captured['score'] == 1
    assert captured['results']['SVM']['status'] == 'selected'
    assert captured['results']['TabPFN']['status'] in ('failed', 'refit_failed')
    assert 'error' in captured['results']['TabPFN']


def test_no_successful_candidate_raises_and_typo_is_not_silently_skipped(monkeypatch, table):
    def missing(*args):
        raise ImportError('missing TabPFN')
    monkeypatch.setattr(support, 'create_tabpfn', missing)
    with pytest.warns(RuntimeWarning), pytest.raises(ValueError, match='No model was trained'):
        train(*table, selected_models=['TabPFN'])
    with pytest.raises(ValueError, match='Unknown selected models'):
        train(*table, selected_models=['TypoPFN'])


def regression_task(tmp_path):
    raw = tmp_path / 'rawdata'
    raw.mkdir()
    X = pd.DataFrame({'x': np.linspace(.1, 2, 60)})
    y = 3 * X.x + .123456789
    training = X.assign(id=[f'train-{i}' for i in range(60)], target=y)[['id', 'x', 'target']]
    test = pd.DataFrame({'id': ['001', '007'], 'x': [.25, .75]})
    sample = test[['id']].assign(target=0.)
    for name, frame in [('train.csv', training), ('test.csv', test), ('sample_submission.csv', sample)]:
        frame.to_csv(raw / name, index=False)
    training.to_csv(tmp_path / 'processed_train.csv', index=False)
    test.to_csv(tmp_path / 'processed_test.csv', index=False)
    return X, y, test, sample


@pytest.mark.parametrize('change', ['valid', 'roundtrip', 'fabricated', 'nan', 'infinity'])
def test_regression_audit_accepts_numeric_roundtrip_and_rejects_fake_values(tmp_path, change):
    from sklearn.linear_model import LinearRegression
    X, y, test, sample = regression_task(tmp_path)
    session = AuditSession(tmp_path)
    model = session.record_training(LinearRegression().fit(X, y), X, y,
        {'linear regression': {'score': -1e-20}}, -1e-20, 'negative_mse')
    values = model.predict(test[['x']])
    if change == 'roundtrip':
        values = [f'{v:.8f}' for v in values]
    elif change == 'fabricated':
        values = values + 1
    elif change in ('nan', 'infinity'):
        values[0] = np.nan if change == 'nan' else np.inf
    sample['target'] = values
    sample.to_csv(tmp_path / 'submission.csv', index=False)
    if change in ('valid', 'roundtrip'):
        assert session.verify_submission()['problem_type'] == 'regression'
    else:
        with pytest.raises(ValueError, match='No verified model prediction'):
            session.verify_submission()


def test_regression_audit_rejects_transformed_targets(tmp_path):
    from sklearn.linear_model import LinearRegression
    X, y, _, _ = regression_task(tmp_path)
    with pytest.raises(ValueError, match='original finite numeric targets'):
        AuditSession(tmp_path).record_training(LinearRegression().fit(X, np.log(y)), X, np.log(y),
            {'linear regression': {'score': -1.}}, -1., 'negative_mse')


def test_modeling_doc_bypasses_stale_chroma_cache(tmp_path):
    from sack.knowledge.tests.test_titanic_workflow_regressions import load_methods
    doc = tmp_path / 'model_build_predict_tools.md'
    doc.write_text('Current TabPFN contract')
    method = load_methods('sack/Tools/retrieve_doc.py', 'RetrieveTool', ['query_tools'])['query_tools']
    tool = SimpleNamespace(doc_path=str(tmp_path))  # no db: cannot accidentally use old vectors
    assert method(tool, 'model selection', 'model_build_predict') == doc.read_text()
