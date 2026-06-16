from datetime import datetime
import fasttext
from glob import glob
import json
import math
import os
from tqdm import tqdm
import psycopg
from psycopg.types.json import Json

from sack.knowledge.knowledge_config import SACKKnowledgeConfig


def _connect_postgres(dbname='postgres'):
    return psycopg.connect(
        host='localhost',
        port=SACKKnowledgeConfig.postgresql_port,
        dbname=dbname,
        user='postgres',
        password='postgres',
        autocommit=True,
    )


def create_columns_embedding_db(db_name):
    try:
        conn = _connect_postgres('postgres')

        cursor = conn.cursor()
        cursor.execute(f'DROP DATABASE IF EXISTS {db_name};')
        cursor.execute(f'CREATE DATABASE {db_name};')
        conn.close()

        conn = _connect_postgres(db_name)
        cursor = conn.cursor()
        cursor.execute('CREATE EXTENSION IF NOT EXISTS vector;')
        cursor.execute(f'''CREATE TABLE {db_name} (
        id text primary key,
        name text,
        data_type text,
        dataset_name text,
        table_name text,
        content_embedding vector(300),
        label_embedding vector(300),
        content_label_embedding vector(600)
        );''')

        cursor.execute(f'CREATE INDEX ON {db_name} (data_type);')
        cursor.execute(f'CREATE INDEX ON {db_name} (dataset_name);')
        cursor.execute(f'CREATE INDEX ON {db_name} (table_name);')
        cursor.execute(f'CREATE INDEX ON {db_name} USING hnsw (content_embedding vector_cosine_ops);')
        cursor.execute(f'CREATE INDEX ON {db_name} USING hnsw (label_embedding vector_cosine_ops);')
        cursor.execute(f'CREATE INDEX ON {db_name} USING hnsw (content_label_embedding vector_cosine_ops);')

        conn.close()
        print(datetime.now(), ': Database Created.')
    except psycopg.Error as e:
        print(datetime.now(), ': Error creating database:', e)

def create_competition_embedding_db(competition_db_name):
    try:
        # 1. 连接默认postgres库，创建新的竞赛数据库
        conn = _connect_postgres('postgres')
        cursor = conn.cursor()
        cursor.execute(f'DROP DATABASE IF EXISTS {competition_db_name};')  # 先删除旧库（如有）
        cursor.execute(f'CREATE DATABASE {competition_db_name};')
        conn.close()

        # 2. 连接新建的竞赛数据库，创建表和索引
        conn = _connect_postgres(competition_db_name)
        cursor = conn.cursor()
        # 鍚敤vector鎵╁睍锛堝瓨鍌ㄥ悜閲忓繀澶囷級
        cursor.execute('CREATE EXTENSION IF NOT EXISTS vector;')

        # 3. 鍒涘缓绔炶禌琛紙瀛楁瀵瑰簲绔炶禌鐗瑰緛锛欼D銆佸悕绉般€佹杩般€佹暟鎹弿杩般€佺粨鏋勫寲瑕佺礌鍙婂祵鍏ュ悜閲忥級
        cursor.execute(f'''CREATE TABLE {competition_db_name} (
            competition_id text primary key,  
            competition_name text,            
            overview text,                    
            data_description text,            
            structured_elements jsonb,        
            overview_embedding vector(300),   
            data_description_embedding vector(300)  
        );''')

        # 4. 鍒涘缓绱㈠紩锛堝姞閫熸煡璇㈠拰鍚戦噺鐩镐技搴︽绱級
        # 4. 创建索引（加速查询和向量相似度检索）
        cursor.execute(f'CREATE INDEX ON {competition_db_name} (competition_name);')
        cursor.execute(f'CREATE INDEX ON {competition_db_name} USING GIN (structured_elements);')  # jsonb瀛楁鐢℅IN绱㈠紩
        # 鍚戦噺瀛楁绱㈠紩锛堢敤hnsw绠楁硶鍔犻€熶綑寮︾浉浼煎害妫€绱級
        cursor.execute(f'CREATE INDEX ON {competition_db_name} USING hnsw (overview_embedding vector_cosine_ops);')
        cursor.execute(f'CREATE INDEX ON {competition_db_name} USING hnsw (data_description_embedding vector_cosine_ops);')

        conn.close()
        print(datetime.now(), ': Competition database created successfully.')
    except psycopg.Error as e:
        print(datetime.now(), ': Error creating competition database:', e)


def insert_columns(column_data, db_name):
    insert_query = f'''INSERT INTO {db_name} (id, name, data_type, dataset_name, table_name, 
                        content_embedding, label_embedding, content_label_embedding) 
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (id) DO NOTHING;'''

    conn = _connect_postgres(db_name)
    cursor = conn.cursor()
    cursor.executemany(insert_query, column_data)
    cursor.close()


def insert_competition(competition_data, db_name):
    insert_query = f'''INSERT INTO {db_name} (
        competition_id, 
        competition_name, 
        overview, 
        data_description, 
        structured_elements, 
        overview_embedding, 
        data_description_embedding
    ) VALUES (%s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (competition_id) DO NOTHING;
    '''

    conn = _connect_postgres(db_name)
    cursor = conn.cursor()
    try:
        # 鍏抽敭淇锛氱敤Json()鍖呰structured_elements锛堢5涓厓绱狅級
        # 关键修复：用Json()包装structured_elements（第5个元素）
        adapted_data = [
            (
                item[0], item[1], item[2], item[3], 
                Json(item[4]),  # 鏄惧紡杞崲涓篜ostgreSQL jsonb绫诲瀷
                item[5], item[6]
            ) 
            for item in competition_data
        ]
        cursor.executemany(insert_query, adapted_data)
    except psycopg.Error as e:
        print(f"Error inserting competition data: {e}")
    finally:
        cursor.close()
        conn.close()  # 纭繚杩炴帴鍏抽棴


def populate_embeddings(column_profiles_path, column_embedding_db_name, competition_embeddings_db_name):

    fasttext_path = os.path.join(SACKKnowledgeConfig.base_dir, 'embeddings/cc.en.300.bin')
    batch_size = 1000

    print(datetime.now() ,': Loading Fasttext embeddings...')
    ft = fasttext.load_model(fasttext_path)

    # go over column profiles:
    print(datetime.now(), ': Populating vector database with column and competition info')
    profile_paths = glob(os.path.join(column_profiles_path, '**', '*.json'), recursive=True)
    column_batch = []
    competition_batch = []
    for profile_path in tqdm(profile_paths):
        with open(profile_path) as f:
            profile = json.load(f)

        if 'embedding' in profile: # column_profile
            if profile['embedding']:
                content_embedding = profile['embedding'] #+ [0] + [math.sqrt(profile['embedding_scaling_factor'])]
            else:
                # boolean column
                content_embedding = [profile['true_ratio']] * 300
            # generate name embeddings and name + value embeddings
            sanitized_name = profile['column_name'].replace('\n', ' ').replace('_', ' ').strip()
            label_embedding = ft.get_sentence_vector(sanitized_name).tolist()
            content_label_embedding = content_embedding + label_embedding

            # store for each column: name, type, id, dataset, table, value embed, name embed, name+value embed
            column_batch.append((profile['column_id'], profile['column_name'], profile['data_type'],
                          profile['dataset_name'], profile['table_name'],
                          str(content_embedding), str(label_embedding), str(content_label_embedding)))
        elif 'overview_embedding' in profile and 'data_description_embedding' in profile: # competition_profile
            overview_embedding = profile['overview_embedding']
            data_description_embedding = profile['data_description_embedding']
            competition_batch.append((profile['competition_id'], profile['competition_name'], profile['overview'],
                      profile['data_description'], profile['structured_elements'],
                      str(overview_embedding), str(data_description_embedding)))
        # else:
        #     print(f"Unexpected profile was detected: {profile}")


        if len(column_batch) >= batch_size:
            insert_columns(column_batch, column_embedding_db_name)
            column_batch = []
        if len(competition_batch) >= batch_size:
            insert_competition(competition_batch, competition_embeddings_db_name)
            competition_batch = []
    if column_batch:
        insert_columns(column_batch, column_embedding_db_name)
    if competition_batch:
        insert_competition(competition_batch, competition_embeddings_db_name)

    print(datetime.now(), ': Database populated with', len(profile_paths), 'columns or competitions.')


