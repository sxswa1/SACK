"""Ensure deterministic preparation preserves the competition's observations."""

import importlib.util
from pathlib import Path

import pandas as pd
import pytest


ROOT = Path(__file__).parents[3]
spec = importlib.util.spec_from_file_location('kaggle_prepare', ROOT / 'scripts/prepare_kaggle_task.py')
preparation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(preparation)


def source_files(folder):
    folder.mkdir()
    (folder / 'train.csv').write_text('PassengerId,Name,Transported\n0001_01,José,True\n0012_03,,False\n')
    (folder / 'test.csv').write_text('PassengerId,Name\n0005_02,Ana\n0041_01,Lee\n')
    (folder / 'sample_submission.csv').write_text('PassengerId,Transported\n0005_02,False\n0041_01,False\n')
    (folder / 'overview.txt').write_text('Test competition')


def test_task_preserves_rows_utf8_empty_values_and_original_identifiers(tmp_path):
    source, repo = tmp_path / 'input', tmp_path / 'repo'
    source_files(source)
    original = {p.name: p.read_bytes() for p in source.iterdir()}
    result = preparation.create_task(repo, 'spaceship-titanic', source)
    task = repo / 'data/competitions/spaceship-titanic'
    assert result['passed']
    train = pd.read_csv(task / 'train.csv', dtype=str, keep_default_na=False)
    assert train.to_dict('list') == {
        'id': ['0001_01', '0012_03'], 'Name': ['José', ''], 'Transported': ['True', 'False']}
    for name, expected in original.items():
        assert (source / name).read_bytes() == expected
        assert (task / 'rawdata' / name).read_bytes() == expected
    with pytest.raises(FileExistsError):
        preparation.create_task(repo, 'spaceship-titanic', source)


def test_preparation_rejects_reordered_sample_identifiers(tmp_path):
    source = tmp_path / 'input'
    source_files(source)
    sample = source / 'sample_submission.csv'
    sample.write_text('PassengerId,Transported\n0041_01,False\n0005_02,False\n')
    with pytest.raises(ValueError, match='match in order'):
        preparation.create_task(tmp_path / 'repo', 'invalid-order', source)
