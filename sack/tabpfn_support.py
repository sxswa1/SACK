"""Optional, reproducible TabPFN candidates for the audited modeling tool."""
import hashlib
from importlib.metadata import version
import os
from pathlib import Path

PACKAGE_VERSION = '2.1.3'
MODEL_VERSION = 'v2'
FAST_VERSION = 'v3.5-fast'
FAST_PACKAGE_VERSION = '9.2.0'
FAST_CHECKPOINT = 'tabpfn-v3.5-fast-20260909.safetensors'
FAST_SHA256 = '14e0b81285bca7a6d1ef121169f27f651f76dff49cad6c0b8779d5c836018550'
FAST_MAX_CONTEXT_ROWS = 1_000_000
CHECKPOINTS = {
    'classifier': ('Prior-Labs/TabPFN-v2-clf', '275f19d2add9c2c0de38f9ebaded3856599fa2e7',
                   'f65a35685aeef42e31b796d9bfa34e68d6fc780bc98e7bff7763802964cf435f'),
    'regressor': ('Prior-Labs/TabPFN-v2-reg', '02a44705ff7790b50cded404bc59adb94da456a1',
                  '2ab5a07d5c41dfe6db9aa7ae106fc6de898326c2765be66505a07e2868c10736'),
}


def checkpoint_digest(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def ensure_checkpoint(directory, kind):
    """Download a fixed revision and check bytes before torch loads the checkpoint."""
    repo, revision, expected = CHECKPOINTS[kind]
    filename = f'tabpfn-v2-{kind}.ckpt'
    path = directory / filename
    if not path.is_file():
        from huggingface_hub import hf_hub_download
        hf_hub_download(repo_id=repo, filename=filename, revision=revision,
                        local_dir=directory)
    if checkpoint_digest(path) != expected:
        raise ValueError(f'TabPFN checkpoint SHA-256 mismatch: {filename}; '
                         'move the unexpected file aside and download the pinned checkpoint')
    return path


def create_tabpfn(X, y, problem_type):
    """Check the full refit size before loading weights or doing any training."""
    variant = os.environ.get('SACK_TABPFN_VARIANT', MODEL_VERSION)
    if variant == FAST_VERSION:
        return create_fast_regressor(X, problem_type)
    if variant != MODEL_VERSION:
        raise ValueError(f'Unknown SACK_TABPFN_VARIANT: {variant}')
    try:
        installed = version('tabpfn')
    except ImportError as exc:
        raise ImportError('Install requirements-tabpfn.txt to enable TabPFN') from exc
    if installed != PACKAGE_VERSION:
        raise ValueError(f'SACK requires tabpfn=={PACKAGE_VERSION}; found {installed}')

    import torch
    from tabpfn import TabPFNClassifier, TabPFNRegressor

    device = os.environ.get('SACK_TABPFN_DEVICE', 'auto')
    if device == 'auto':
        device = 'cuda' if torch.cuda.is_available() else 'cpu'
    if device != 'cpu' and device != 'cuda' and not device.startswith('cuda:'):
        raise ValueError('SACK_TABPFN_DEVICE must be auto, cpu, cuda or cuda:<index>')
    if device.startswith('cuda') and not torch.cuda.is_available():
        raise ValueError('CUDA was requested for TabPFN but is unavailable')
    # Upstream exposes this explicit opt-in for CPU performance, independently
    # of its 10k-row pretraining boundary. Keep the default CPU guard intact.
    allow_large_cpu = os.environ.get('TABPFN_ALLOW_CPU_LARGE_DATASET', '').strip().lower() in {
        '1', 'true', 'yes', 'on', 't', 'y'}
    limit = 1000 if device == 'cpu' and not allow_large_cpu else 10000
    if len(X) > limit or X.shape[1] > 500:
        raise ValueError(f'TabPFN v2 limit on {device}: {limit} rows and 500 features; '
                         f'got {len(X)} rows and {X.shape[1]} features')
    if problem_type != 'regression' and len(set(y)) > 10:
        raise ValueError('TabPFN v2 supports at most 10 classes')

    n_estimators = int(os.environ.get('SACK_TABPFN_N_ESTIMATORS', '4'))
    n_jobs = int(os.environ.get('SACK_TABPFN_N_JOBS', '1'))
    if n_estimators < 1 or n_jobs < 1:
        raise ValueError('TabPFN n_estimators and n_jobs must be positive integers')
    regression = problem_type == 'regression'
    kind = 'regressor' if regression else 'classifier'
    directory = Path(os.environ.get('SACK_TABPFN_MODEL_DIR', '~/.cache/tabpfn')).expanduser()
    directory.mkdir(parents=True, exist_ok=True)
    path = ensure_checkpoint(directory, kind)
    estimator = (TabPFNRegressor if regression else TabPFNClassifier)(
        model_path=path, device=device, n_estimators=n_estimators,
        random_state=42, n_jobs=n_jobs, ignore_pretraining_limits=False)
    estimator._sack_tabpfn_details = {
        'package_version': installed, 'model_version': MODEL_VERSION,
        'checkpoint': path.name, 'checkpoint_revision': CHECKPOINTS[kind][1],
        'device': device, 'n_estimators': n_estimators,
        'n_jobs': n_jobs,
        'allow_cpu_large_dataset': device == 'cpu' and allow_large_cpu,
        'full_training_row_limit': limit,
    }
    return estimator


def model_details(model):
    details = dict(getattr(model, '_sack_tabpfn_details', {}))
    if details:
        path = Path(model.model_path)
        if path.is_file():
            details['checkpoint_sha256'] = checkpoint_digest(path)
    return details


def create_fast_regressor(X, problem_type):
    if problem_type != 'regression':
        raise ValueError('SACK TabPFN-3.5-Fast currently supports regression')
    if X.shape[1] > 500:
        raise ValueError('SACK TabPFN-3.5-Fast supports up to 500 input features')
    try:
        installed = version('tabpfn')
    except ImportError as exc:
        raise ImportError('Install requirements-tabpfn-fast.txt to enable TabPFN-3.5-Fast') from exc
    if installed != FAST_PACKAGE_VERSION:
        raise ValueError(f'SACK TabPFN-3.5-Fast requires tabpfn=={FAST_PACKAGE_VERSION}; found {installed}')

    import torch

    device = os.environ.get('SACK_TABPFN_DEVICE', 'auto')
    if device == 'auto':
        device = 'cuda'
    if not (device == 'cuda' or device.startswith('cuda:')) or not torch.cuda.is_available():
        raise ValueError('SACK TabPFN-3.5-Fast requires a CUDA device')
    shard_rows = int(os.environ.get('SACK_TABPFN_FAST_SHARD_ROWS', '250000'))
    n_estimators = int(os.environ.get('SACK_TABPFN_N_ESTIMATORS', '1'))
    if not 1 <= shard_rows <= FAST_MAX_CONTEXT_ROWS or n_estimators < 1:
        raise ValueError('TabPFN shard rows must be within 1–1000000 and n_estimators must be positive')
    directory = Path(os.environ.get('SACK_TABPFN_MODEL_DIR', '~/.cache/tabpfn')).expanduser()
    path = directory / FAST_CHECKPOINT
    if not path.is_file() or checkpoint_digest(path) != FAST_SHA256:
        raise ValueError(f'Provide the pinned TabPFN-3.5-Fast checkpoint with matching SHA-256 at {path}')
    log_target = os.environ.get('SACK_TABPFN_LOG1P', '0') == '1'
    return TabPFNShardedRegressor(path, device, shard_rows, n_estimators, log_target)


class TabPFNShardedRegressor:
    """Evaluate disjoint contexts sequentially so their KV caches never coexist."""

    def __init__(self, model_path, device, shard_rows, n_estimators, log_target):
        self.model_path = model_path
        self.device = device
        self.shard_rows = shard_rows
        self.n_estimators = n_estimators
        self.log_target = log_target
        self._sack_tabpfn_details = {
            'package_version': FAST_PACKAGE_VERSION,
            'model_version': FAST_VERSION,
            'checkpoint': model_path.name,
            'device': device,
            'n_estimators': n_estimators,
            'max_shard_rows': shard_rows,
            'target_transform': 'log1p' if log_target else 'identity',
        }

    def fit(self, X, y):
        import numpy as np

        target = np.asarray(y, dtype=float)
        if target.shape != (len(X),) or not len(X) or not np.isfinite(target).all():
            raise ValueError('TabPFN-3.5-Fast requires a finite numeric target per training row')
        if self.log_target and np.any(target < 0):
            raise ValueError('The TabPFN log1p target transform requires nonnegative targets')
        self._X = X
        self._y = np.log1p(target) if self.log_target else target
        order = np.random.default_rng(42).permutation(len(X))
        shard_count = (len(X) + self.shard_rows - 1) // self.shard_rows
        self._shards = np.array_split(order, shard_count)
        self._sack_tabpfn_details['shard_rows'] = [len(rows) for rows in self._shards]
        return self

    def predict(self, X):
        import numpy as np
        import torch
        from tabpfn import TabPFNRegressor

        if not X.columns.equals(self._X.columns):
            raise ValueError('TabPFN prediction columns must match the fitted feature order')
        output = np.zeros(len(X), dtype=np.float64)
        for rows in self._shards:
            model = TabPFNRegressor(
                model_path=self.model_path, device=self.device, n_estimators=self.n_estimators,
                fit_mode='fit_with_cache', random_state=42, ignore_pretraining_limits=False,
            )
            try:
                model.fit(self._X.iloc[rows], self._y[rows])
                if model.inference_config_.SUBSAMPLE_SAMPLES is not None:
                    raise ValueError('Unexpected internal subsampling in TabPFN-3.5-Fast')
                weight = len(rows) / len(self._X)
                for start in range(0, len(X), 10_000):
                    stop = min(start + 10_000, len(X))
                    predictions = model.predict(X.iloc[start:stop])
                    if predictions.shape != (stop - start,) or not np.isfinite(predictions).all():
                        raise ValueError('TabPFN-3.5-Fast produced invalid predictions')
                    output[start:stop] += weight * predictions
            finally:
                del model
                torch.cuda.empty_cache()
        return np.expm1(np.maximum(output, 0.0)) if self.log_target else output
