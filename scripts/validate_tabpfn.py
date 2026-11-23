"""Exercise real TabPFN weights through SACK training, prediction and submission audit.

Uses bundled sklearn datasets; does not call LLMs, databases or Kaggle.
Output must be a new directory, so historical experiment files are preserved.
"""
import argparse
from importlib.metadata import version
import json
import os
from pathlib import Path
import platform
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--model-dir', type=Path, required=True)
    parser.add_argument('--device', default='cpu')
    parser.add_argument('--n-estimators', type=int, default=1)
    args = parser.parse_args()
    os.environ.update(SACK_TABPFN_DEVICE=args.device,
                      SACK_TABPFN_MODEL_DIR=str(args.model_dir.resolve()),
                      SACK_TABPFN_N_ESTIMATORS=str(args.n_estimators),
                      SACK_TABPFN_N_JOBS='1')
    # Avoid excessive CPU threading on small validation tasks.
    import torch
    torch.set_num_threads(2)
    import numpy as np
    import pandas as pd
    from sklearn.datasets import load_breast_cancer, load_iris, load_diabetes
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import accuracy_score, mean_squared_error
    from sack.model_audit import run

    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=False)
    summary = {'python': platform.python_version(), 'platform': platform.platform(),
               'versions': {n: version(n) for n in ('tabpfn', 'torch', 'numpy', 'pandas',
                                                   'scipy', 'scikit-learn')},
               'device': args.device, 'n_estimators': args.n_estimators, 'cases': []}
    try:
        for name, loader, problem, count in [
            ('breast-cancer', load_breast_cancer, 'binary', 240),
            ('iris', load_iris, 'multiclass', 150),
            ('diabetes', load_diabetes, 'regression', 200),
        ]:
            X, y = loader(return_X_y=True, as_frame=True)
            X, y = X.iloc[:count], y.iloc[:count]
            X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=.25,
                random_state=42, stratify=y if problem != 'regression' else None)
            task = output / name
            raw = task / 'rawdata'
            raw.mkdir(parents=True)
            training = X_train.reset_index(drop=True).copy()
            training.insert(0, 'id', [f'train-{i:04d}' for i in range(len(training))])
            training['target'] = y_train.to_numpy()
            test = X_test.reset_index(drop=True).copy()
            test.insert(0, 'id', [f'test-{i:04d}' for i in range(len(test))])
            sample = test[['id']].assign(target=0)
            for filename, frame in [('train.csv', training), ('test.csv', test),
                                     ('sample_submission.csv', sample)]:
                frame.to_csv(raw / filename, index=False)
            training.to_csv(task / 'processed_train.csv', index=False)
            test.to_csv(task / 'processed_test.csv', index=False)
            script = task / 'modeling.py'
            script.write_text('''from pathlib import Path
import pandas as pd
from sack.Tools.ml_tools import train_and_validation_and_select_the_best_model
task = Path(__file__).parent
training = pd.read_csv(task / 'processed_train.csv')
test = pd.read_csv(task / 'processed_test.csv')
features = [c for c in training if c not in ('id', 'target')]
model = train_and_validation_and_select_the_best_model(training[features], training['target'],
    problem_type=PROBLEM, selected_models=['TabPFN'])
sample = pd.read_csv(task / 'rawdata/sample_submission.csv', dtype={'id': str})
sample['target'] = model.predict(test[features])
sample.to_csv(task / 'submission.csv', index=False)
'''.replace('PROBLEM', repr(problem)), encoding='utf-8')
            receipt = task / 'training_execution.json'
            start = time.monotonic()
            run(script, task, receipt, 'tabpfn-validation')
            evidence = json.loads(receipt.read_text())
            if not evidence['passed'] or not evidence['model_class'].startswith('TabPFN'):
                raise RuntimeError(f'{name} did not produce audited TabPFN predictions')
            predictions = pd.read_csv(task / 'submission.csv')['target']
            score = (mean_squared_error(y_test, predictions) if problem == 'regression'
                     else accuracy_score(y_test, predictions))
            if not np.isfinite(score):
                raise RuntimeError('Nonfinite held-out score')
            case = {'name': name, 'problem_type': problem, 'passed': True,
                    'training_rows': len(training), 'prediction_rows': len(test),
                    'elapsed_seconds': round(time.monotonic() - start, 3),
                    'heldout_metric': 'mse' if problem == 'regression' else 'accuracy',
                    'heldout_score': float(score), 'evidence': evidence}
            summary['cases'].append(case)
            print(json.dumps({k: v for k, v in case.items() if k != 'evidence'}), flush=True)
        summary['passed'] = True
    except BaseException as exc:
        summary.update(passed=False, error=f'{type(exc).__name__}: {exc}')
        raise
    finally:
        (output / 'summary.json').write_text(json.dumps(summary, indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
