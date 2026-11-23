"""String conversion must not hide missing values from downstream cleaning."""
import numpy as np
import pandas as pd

from sack.Tools.ml_tools import (
    convert_data_types,
    fill_missing_values,
    remove_columns_with_missing_data,
)


def test_string_conversion_preserves_missingness_through_cleaning_and_csv(tmp_path):
    frame = pd.DataFrame({
        'id': [11, 12, 13, 14],
        'category': ['brick', None, np.nan, pd.NA],
        'number_as_text': [1, 2, None, 4],
        'SalePrice': [100, 200, 300, 400],
    }, index=[8, 2, 9, 3])
    missing = frame[['category', 'number_as_text']].isna()
    original_ids, original_target = frame.id.copy(), frame.SalePrice.copy()
    converted = convert_data_types(frame, ['category', 'number_as_text'], 'str')
    pd.testing.assert_frame_equal(converted[['category', 'number_as_text']].isna(), missing)
    assert converted.loc[8, 'number_as_text'] == '1.0'
    assert list(converted.index) == [8, 2, 9, 3]
    # A genuinely sparse column must still be visible to the drop decision.
    reduced = remove_columns_with_missing_data(converted, thresh=0.5)
    assert 'category' not in reduced.columns
    assert 'number_as_text' in reduced.columns
    cleaned = fill_missing_values(reduced.copy(), 'number_as_text', method='constant', fill_value='Missing')
    path = tmp_path / 'cleaned.csv'
    cleaned.to_csv(path, index=False)
    roundtrip = pd.read_csv(path)
    assert not roundtrip.isna().any().any()
    assert roundtrip.id.tolist() == original_ids.tolist()
    assert roundtrip.SalePrice.tolist() == original_target.tolist()
    assert roundtrip.number_as_text.tolist() == ['1.0', '2.0', 'Missing', '4.0']
