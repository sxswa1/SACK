import io
from typing import Dict, List, Optional, Tuple, Union

import pandas as pd
import psycopg
from SPARQLWrapper import CSV, JSON, SPARQLWrapper


def connect_to_graphdb(endpoint, graphdb_repo):
    return SPARQLWrapper(f"{endpoint}/repositories/{graphdb_repo}")


def query_graphdb(graphdb_conn: SPARQLWrapper, query, return_type="csv"):
    graphdb_conn.setQuery(query)
    if return_type == "csv":
        graphdb_conn.setReturnFormat(CSV)
        results = graphdb_conn.queryAndConvert()
        return pd.read_csv(io.BytesIO(results))
    if return_type == "json":
        graphdb_conn.setReturnFormat(JSON)
        results = graphdb_conn.queryAndConvert()
        return results["results"]["bindings"]
    raise ValueError(f"Return type {return_type} is not supported")


def connect_to_postgres(
    host: str = "localhost",
    user: str = "postgres",
    password: str = "postgres",
    dbname: str = "postgres",
    port: int = 5432,
) -> psycopg.Connection:
    try:
        return psycopg.connect(host=host, user=user, password=password, dbname=dbname, port=port)
    except psycopg.Error as e:
        raise RuntimeError(f"PostgreSQL connection failed: {e}") from e


def query_postgres(
    pg_conn: psycopg.Connection,
    query: str,
    params: Optional[Tuple] = None,
    return_type: str = "csv",
) -> Union[pd.DataFrame, List[Dict]]:
    if params is None:
        params = ()

    try:
        with pg_conn.cursor() as cur:
            cur.execute(query, params)
            results = cur.fetchall()
            columns = [desc[0] for desc in cur.description]

        if return_type == "csv":
            return pd.DataFrame(results, columns=columns)
        if return_type == "json":
            return [dict(zip(columns, row)) for row in results]
        raise ValueError(f"Return type {return_type} is not supported")
    except psycopg.Error as e:
        pg_conn.rollback()
        raise RuntimeError(f"PostgreSQL query failed: SQL={query}, Params={params}, Error={e}") from e
