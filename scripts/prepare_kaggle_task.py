"""Create a new task from Kaggle CSVs without changing IDs or observations.

Preparation is deterministic; the SACK workflow can then start at
``Understand Background`` in both EDA and DSP modes.
"""

import argparse
import hashlib
import json
from pathlib import Path
import shutil

import pandas as pd


def prepare(workspace):
    workspace = Path(workspace)
    raw = workspace / 'rawdata'
    frames = {}
    original_ids = {}
    hashes = {}
    original_tables = {}
    for filename in ['train.csv', 'test.csv', 'sample_submission.csv']:
        path = raw / filename
        hashes[filename] = hashlib.sha256(path.read_bytes()).hexdigest()
        frame = pd.read_csv(path, dtype=str, keep_default_na=False, encoding='utf-8-sig',
                            skip_blank_lines=False)
        original_tables[filename] = {'rows': len(frame), 'columns': list(frame.columns)}
        candidates = [name for name in frame.columns if name.lower() in {'id', 'passengerid'}]
        if len(candidates) != 1 or frame.empty or not frame.columns.is_unique:
            raise ValueError('Ambiguous schema or empty input: ' + filename)
        source_id = candidates[0]
        ids = frame[source_id]
        if ids.str.strip().eq('').any() or ids.duplicated().any():
            raise ValueError('Missing or duplicate source identifiers: ' + filename)
        original_ids[filename] = ids.tolist()
        frame = frame.rename(columns={source_id: 'id'})
        frames[filename] = frame[['id'] + [c for c in frame.columns if c != 'id']]
    if original_ids['test.csv'] != original_ids['sample_submission.csv']:
        raise ValueError('Test and sample identifiers must match in order')
    targets = set(frames['sample_submission.csv'].columns) - {'id'}
    if not targets or set(frames['train.csv'].columns) != set(frames['test.csv'].columns) | targets:
        raise ValueError('Train, test and submission columns do not align')
    if set(frames['test.csv'].columns) & targets:
        raise ValueError('Test contains target columns')
    for filename, frame in frames.items():
        frame.to_csv(workspace / filename, index=False, encoding='utf-8')
        saved = pd.read_csv(workspace / filename, dtype=str, keep_default_na=False)
        if not saved.equals(frame.reset_index(drop=True)):
            raise ValueError('CSV roundtrip changed values: ' + filename)
    overview = raw / 'overview.txt'
    hashes['overview.txt'] = hashlib.sha256(overview.read_bytes()).hexdigest()
    (workspace / 'overview.txt').write_text(
        overview.read_text(encoding='utf-8-sig') + '\n\nPreparation: raw CSVs are copied '
        'without removing rows, imputing, encoding or changing targets. The original '
        'ID column is renamed to id; identifier values and row order are preserved. '
        'Test and sample_submission contain the same ordered identifiers.\n', encoding='utf-8')
    if (raw / 'data_description.txt').exists():
        shutil.copy2(raw / 'data_description.txt', workspace / 'data_description.txt')
        hashes['data_description.txt'] = hashlib.sha256((raw / 'data_description.txt').read_bytes()).hexdigest()
    evidence = {'method': 'deterministic CSV standardization', 'passed': True,
                'raw_sha256': hashes, 'tables': original_tables,
                'id_values_preserved': True, 'row_order_preserved': True,
                'targets': sorted(targets)}
    stage = workspace / 'data_preparation'
    stage.mkdir(exist_ok=True)
    (stage / 'preparation.json').write_text(json.dumps(evidence, indent=2) + '\n')
    (stage / 'report.txt').write_text(
        'Deterministic preparation completed. See preparation.json for verified row '
        'counts, schema and raw SHA256. Original IDs, targets and row order are preserved. '
        'Only the ID column name is standardized to id. No model or LLM was used.\n')
    return evidence


def create_task(repo, competition, source):
    repo, source = Path(repo), Path(source)
    destination = repo / 'data/competitions' / competition
    if destination.exists() or (repo / 'data/eda_competitions' / competition).exists():
        raise FileExistsError('Refusing to overwrite an existing task: ' + competition)
    destination.mkdir(parents=True)
    raw = destination / 'rawdata'
    raw.mkdir()
    for name in ['train.csv', 'test.csv', 'sample_submission.csv', 'overview.txt', 'data_description.txt']:
        if (source / name).is_file():
            shutil.copy2(source / name, raw / name)
    return prepare(destination)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', required=True)
    parser.add_argument('--competition', required=True)
    parser.add_argument('--source', required=True)
    args = parser.parse_args()
    print(json.dumps(create_task(args.repo, args.competition, args.source), indent=2))
