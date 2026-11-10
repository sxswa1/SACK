"""Optional, reproducible TabPFN v2 candidate for SACK's modeling tool."""
import hashlib
from importlib.metadata import version
import os
from pathlib import Path

PACKAGE_VERSION = '2.1.3'
MODEL_VERSION = 'v2'
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
    limit = 1000 if device == 'cpu' else 10000
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
    }
    return estimator


def model_details(model):
    details = dict(getattr(model, '_sack_tabpfn_details', {}))
    if details:
        path = Path(model.model_path)
        if path.is_file():
            details['checkpoint_sha256'] = checkpoint_digest(path)
    return details
