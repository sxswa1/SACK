import urllib


def encode(entity):
    return urllib.parse.quote_plus(entity)  # 字符串的url安全化处理（如用"+"替代" "）

def generate_column_id(data_source: str, dataset_name: str, table_name: str, column_name: str):
    return encode(data_source) + '/' + encode(dataset_name) + '/' + encode(table_name) + '/' + encode(column_name)  # 缁勫悎鏁版嵁婧愬埌鍒楀悕瀵瑰簲鐨勭殑url  涔熷氨鏄墍璋撶殑id


def generate_table_id(data_source: str, dataset_name: str, table_name: str):
    return encode(data_source) + '/' + encode(dataset_name) + '/' + encode(table_name)  # 缁勫悎鏁版嵁婧愬埌琛ㄥ悕鐨剈rl


def generate_dataset_id(data_source: str, dataset_name: str): # 缁勫悎鏁版嵁婧愬拰鏁版嵁闆嗗悕绉扮殑url
    return encode(data_source) + '/' + encode(dataset_name)

def generate_competition_id(data_source: str, competition_name: str):
    """生成竞赛ID，格式: data_source/competition_name"""
    return encode(data_source) + '/' + encode(competition_name)
