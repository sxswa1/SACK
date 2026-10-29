"""Framework-owned evidence for the generated modeling stage.

Evidence is produced after real tool execution, not accepted from model prose.
This checks workflow correctness; it is not a sandbox for hostile Python code.
"""
import argparse
import hashlib
import json
from pathlib import Path
import runpy

_active_session = None


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def label(value):
    import numpy as np
    if isinstance(value, (bool, np.bool_)):
        return str(bool(value))
    if isinstance(value, (int, float, np.number)) and np.isfinite(value):
        return str(int(value)) if float(value).is_integer() else str(value)
    return str(value)


class AuditedModel:
    def __init__(self, model, session, record, mapping):
        self._model, self._session, self._record, self._mapping = model, session, record, mapping

    def __getattr__(self, name):
        return getattr(self._model, name)

    def predict(self, X):
        predictions = self._model.predict(X)
        if self._session.matches_features(X, 'processed_test.csv'):
            values = [self._mapping.get(label(v), label(v)) for v in predictions]
            self._session.predictions.append((self._record, values))
        return predictions


class AuditSession:
    def __init__(self, task):
        self.task = Path(task)
        self.records = []
        self.predictions = []

    def source_tables(self):
        import pandas as pd
        frames = [pd.read_csv(self.task / 'rawdata' / name, dtype=str, keep_default_na=False)
                  for name in ('train.csv', 'test.csv', 'sample_submission.csv')]
        train, test, sample = frames
        if len(sample.columns) != 2:
            raise ValueError('Training audit currently requires one prediction target')
        identifier, target = sample.columns
        if test[identifier].tolist() != sample[identifier].tolist():
            raise ValueError('Raw test and submission identifiers do not align')
        return train, test, identifier, target

    def matches_features(self, X, filename):
        import pandas as pd
        import numpy as np
        if not isinstance(X, pd.DataFrame) or X.empty or not X.columns.is_unique:
            return False
        frame = pd.read_csv(self.task / filename)
        _, _, _, target = self.source_tables()
        if 'id' in X.columns or target in X.columns or not set(X.columns).issubset(frame.columns):
            return False
        reference = frame.loc[:, X.columns]
        if X.shape != reference.shape:
            return False
        try:
            pd.testing.assert_frame_equal(X.reset_index(drop=True), reference.reset_index(drop=True),
                                          check_dtype=False, check_exact=False, rtol=1e-10, atol=1e-12)
        except AssertionError:
            return False
        return not X.isna().any().any() and all(
            np.isfinite(X[c]).all() for c in X.select_dtypes(include='number').columns)

    def record_training(self, model, X, y, results, score, metric):
        import math
        import pandas as pd
        raw_train, raw_test, identifier, target = self.source_tables()
        if not self.matches_features(X, 'processed_train.csv') or len(y) != len(raw_train):
            raise ValueError('Audited training requires the full ordered processed_train predictors and target')
        for filename, raw in [('processed_train.csv', raw_train), ('processed_test.csv', raw_test)]:
            prepared = pd.read_csv(self.task / filename, dtype=str, keep_default_na=False)
            if prepared['id'].tolist() != raw[identifier].tolist():
                raise ValueError('Processed IDs/row order differ from raw data: ' + filename)
        mapping, forward = {}, {}
        for transformed, original in zip(y, raw_train[target]):
            transformed = label(transformed)
            if ((transformed in mapping and mapping[transformed] != original) or
                    (original in forward and forward[original] != transformed)):
                raise ValueError('Training target is not a consistent encoding of the original labels')
            mapping[transformed] = original
            forward[original] = transformed
        if not results or not math.isfinite(float(score)):
            raise ValueError('Measured validation results are missing or nonfinite')
        record = {'model_class': type(model).__name__, 'training_rows': len(X),
                  'validation_metric': metric, 'validation_score': float(score),
                  'candidate_results': results, 'full_data_refit': True,
                  'input_sha256': {name: digest(self.task / name) for name in
                      ('processed_train.csv', 'processed_test.csv', 'rawdata/train.csv',
                       'rawdata/test.csv', 'rawdata/sample_submission.csv')}}
        self.records.append(record)
        return AuditedModel(model, self, record, mapping)

    def verify_submission(self):
        import pandas as pd
        raw_train, raw_test, identifier, target = self.source_tables()
        submission = pd.read_csv(self.task / 'submission.csv', dtype=str, keep_default_na=False)
        if list(submission.columns) not in ([identifier, target], ['id', target]):
            raise ValueError('Submission columns must preserve ID and original target name')
        if submission.iloc[:, 0].tolist() != raw_test[identifier].tolist():
            raise ValueError('Submission IDs or row order differ from the original test set')
        values = submission[target].tolist()
        if not values or not set(values).issubset(set(raw_train[target])):
            raise ValueError('Submission labels differ from the original training labels')
        for record, predictions in reversed(self.predictions):
            if values == predictions and all(digest(self.task / name) == expected
                                              for name, expected in record['input_sha256'].items()):
                return {**record, 'prediction_rows': len(values),
                        'submission_sha256': digest(self.task / 'submission.csv')}
        raise ValueError('No verified model prediction matches submission.csv. Call the real training '
                         'tool, then model.predict on ordered processed_test predictors; decode labels '
                         'back to their original spelling. Random/placeholder predictions are invalid.')


def record_training(model, X, y, results, score, metric):
    if _active_session is None:
        return model
    return _active_session.record_training(model, X, y, results, score, metric)


def validate_receipt(task, script, receipt, run_id=None):
    """Reject stale evidence after regeneration or output modification."""
    data = json.loads(Path(receipt).read_text())
    if data.get('passed') is not True or (run_id is not None and data.get('run_id') != run_id):
        raise ValueError('Missing successful training evidence for the current execution')
    if data.get('script_sha256') != digest(script):
        raise ValueError('Training evidence belongs to a different generated script')
    if data.get('submission_sha256') != digest(Path(task) / 'submission.csv'):
        raise ValueError('Submission changed after audited prediction')
    for name, expected in data['input_sha256'].items():
        if digest(Path(task) / name) != expected:
            raise ValueError('Training input changed after audited execution: ' + name)
    return data


def run(script, task, receipt, run_id):
    global _active_session
    script, task, receipt = Path(script).resolve(), Path(task).resolve(), Path(receipt).resolve()
    data = {'passed': False, 'run_id': run_id, 'script_sha256': digest(script)}
    receipt.write_text(json.dumps(data))  # invalidate any earlier success before execution
    _active_session = AuditSession(task)
    try:
        runpy.run_path(str(script), run_name='__main__')
        data.update(_active_session.verify_submission(), passed=True)
    except BaseException as exc:
        data.update(passed=False, error=f'{type(exc).__name__}: {exc}')
        raise
    finally:
        receipt.write_text(json.dumps(data, indent=2, allow_nan=False))
        _active_session = None


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    for option in ('script', 'task', 'receipt', 'run-id'):
        parser.add_argument('--' + option, required=True)
    args = parser.parse_args()
    # Hooks imported by Tools.ml_tools must share the canonical module's session.
    from sack.model_audit import run as audited_run
    audited_run(args.script, args.task, args.receipt, args.run_id)
