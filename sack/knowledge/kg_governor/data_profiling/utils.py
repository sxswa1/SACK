import urllib


def encode(entity):
    return urllib.parse.quote_plus(entity)  # 字符串的url安全化处理（如用"+"替代" "）

def generate_column_id(data_source: str, dataset_name: str, table_name: str, column_name: str):
    return encode(data_source) + '/' + encode(dataset_name) + '/' + encode(table_name) + '/' + encode(column_name)  # 组合数据源和列名的 URL，作为列 ID。


def generate_table_id(data_source: str, dataset_name: str, table_name: str):
    return encode(data_source) + '/' + encode(dataset_name) + '/' + encode(table_name)  # 组合数据源到表名的url


def generate_dataset_id(data_source: str, dataset_name: str): # 组合数据源和数据集名称的url
    return encode(data_source) + '/' + encode(dataset_name)

def generate_competition_id(data_source: str, competition_name: str):
    """生成竞赛ID，格式: data_source/competition_name"""
    return encode(data_source) + '/' + encode(competition_name)
