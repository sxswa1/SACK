import ast
import pandas as pd
import zlib
import fasttext
import os
import re
import numpy as np
import seaborn as sns
from graphviz import Digraph
from camelsplit import camelsplit
from matplotlib import pyplot as plt
from sack.knowledge.kg_governor.data_global_schema_builder.utils.utils import Label
from sack.knowledge.api.helpers.helper import *
from sack.knowledge.knowledge_config import SACKKnowledgeConfig
from sack.knowledge.api.edainsight_similarity import *


PREFIXES = """
    PREFIX sack: <http://sack.local/ontology/>
    PREFIX data:   <http://sack.local/ontology/data/>
    PREFIX schema: <http://schema.org/>
    PREFIX rdf:    <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    PREFIX pipeline: <http://sack.local/ontology/pipeline/>
    PREFIX lib: <http://sack.local/resource/library/> 
    PREFIX sackData: <http://sack.local/ontology/data/>
    """


def _configured_graph_store(config):
    """Return the optional domain store used during GraphDB/TuGraph migration."""

    return config.get("graph_store") if isinstance(config, dict) else None


def get_competition_name(config: dict, competition_uri: str) -> str:
    graph_store = _configured_graph_store(config)
    if graph_store is not None:
        return graph_store.get_competition_name(competition_uri) or "Unknown"
    graphdb_conn = config["graphdb_conn"]
    query = PREFIXES + f"""
    SELECT ?comp_name
    WHERE {{ <{competition_uri}> a sack:Dataset ; rdfs:label ?comp_name . }}
    """
    results = query_graphdb(graphdb_conn, query, return_type="json")
    return results[0]["comp_name"]["value"] if results else "Unknown"


def query_sack_knowledge(config, rdf_query):
    return query_graphdb(config, PREFIXES + rdf_query)


def get_datasets_info(config, show_query):
    query = PREFIXES + """
    SELECT ?Dataset (count(?table_id) as ?Number_of_tables)
    WHERE
    {
        ?dataset_id	rdf:type	sack:Dataset	.
        ?dataset_id schema:name	?Dataset	    .
      	?table_id	sack:isPartOf	?dataset_id	.
    }
    group by ?Dataset """
    if show_query:
        print(query)
    return query_graphdb(config, query)


def get_tables_info(config, dataset: str, show_query):
    if dataset:
        dataset = '?dataset_id schema:name "{}" .'.format(dataset)
    query = PREFIXES + """
    SELECT ?Table ?Dataset ?Path_to_table
    WHERE
    {
        ?table_id	rdf:type            sack:Table	.
        %s
        ?table_id	sack:isPartOf     ?dataset_id		.
        ?table_id  	schema:name			?Table  		.
        ?table_id	data:hasFilePath	?Path_to_table	.
        ?dataset_id	schema:name			?Dataset	    .	
    }""" % dataset
    if show_query:
        print(query)
    return query_graphdb(config, query)


def get_top_k_tables(pairs: list):
    top_k = {}
    dataset = {}
    path = {}
    for p in pairs:
        if p[0] not in top_k:
            top_k[p[0]] = p[1]
            dataset[p[0]] = p[2]
            path[p[0]] = p[3]
        else:
            updated_score = top_k.get(p[0]) + p[1]
            top_k[p[0]] = updated_score

    scores = top_k
    top_k = list(dict(sorted(top_k.items(), key=lambda item: item[1], reverse=True)).keys())
    top_k = [list(ele) for ele in top_k]

    for pair in top_k:
        c1 = pair[0]
        c2 = pair[1]
        pair = pair.extend([scores.get((c1, c2)), dataset.get((c1, c2)), path.get((c1, c2))])

    return top_k


def recommend_tables(config, dataset: str, table: str, k: int, relation: str, show_query: bool):
    query = PREFIXES + """
    SELECT ?table_name1 ?table_name2 ?certainty ?dataset2_n ?path
    WHERE
    {
        ?table_id	schema:name		"%s"	        .
      	?table_id	schema:name		?table_name1	.
      	?dataset_id schema:name     "%s"            .
      	?table_id   sack:isPartOf ?dataset_id     .
      	?column_id	sack:isPartOf ?table_id		.

      	<<?column_id %s	?column_id2>>	data:withCertainty	?certainty	. 
      	?column_id2 sack:isPartOf	?table_id2		.
      	?table_id2	schema:name		?table_name2	.
      	?table_id2  data:hasFilePath ?path          .
      	?table_id2  sack:isPartOf ?dataset2       .
      	?dataset2   schema:name     ?dataset2_n     .
    }
    """ % (table, dataset, relation)
    if show_query:
        print(query)

    res = query_graphdb(config, query, return_type='json')
    result = []
    for r in res:
        table1 = r["table_name1"]["value"]
        table2 = r["table_name2"]["value"]
        certainty = float(r["certainty"]["value"])
        dataset = r["dataset2_n"]["value"]
        path = r["path"]["value"]
        result.append([(table1, table2), certainty, dataset, path])

    result = get_top_k_tables(result)[:k]
    table = list(map(lambda x: x[1], result))
    scores = list(map(lambda x: x[2], result))
    dataset = list(map(lambda x: x[3], result))
    path = list(map(lambda x: x[4], result))
    return pd.DataFrame({'Dataset': dataset, 'Recommended_table': table,
                         'Score': scores, 'Path_to_table': path})


def show_graph_info(config, show_query):
    query1 = PREFIXES + """
    SELECT (COUNT(?Dataset) as ?Datasets)
    WHERE
    {
        ?Dataset    rdf:type sack:Dataset     .
    }
    """
    query2 = PREFIXES + """
    SELECT  (COUNT(?Table) as ?Tables)
    WHERE
    {
        ?Table      rdf:type        sack:Table    ;
                    sack:isPartOf ?Dataset        .
        ?Dataset    rdf:type        sack:Dataset  . 
    } 
    """
    query3 = PREFIXES + """
    SELECT (COUNT(?Pipeline) as ?Pipelines)
    WHERE
    {
        ?Pipeline   rdf:type    sack:Pipeline ;
                    sack:isPartOf ?Dataset    .
        ?Dataset    rdf:type    sack:Dataset  .
    }
    """
    query4 = PREFIXES + """
    SELECT  (COUNT(?Column) as ?Columns)
    WHERE
    {
        ?Column     rdf:type        sack:Column   ;
                    sack:isPartOf ?Table          .
        ?Table      rdf:type        sack:Table    . 
    } 
    """
    if show_query:
        print(query1, '\n', query3, '\n', query2, '\n', query4)
    dataset = query_graphdb(config, query1)
    tables = query_graphdb(config, query2)
    pipelines = query_graphdb(config, query3)
    columns = query_graphdb(config, query4)
    return pd.concat([dataset, pipelines, tables, columns], axis=1)


def get_table_path(config, dataset, table):
    query = PREFIXES + """
    SELECT ?table_path
	WHERE
	{
      ?dataset	schema:name				"%s"	;
      			rdf:type				sack:Dataset	.
      ?table	schema:name				"%s"	;
      			rdf:type				sack:Table	;
      			data:hasFilePath		?table_path		.			
    }
    """ % (dataset, table)

    res = query_graphdb(config, query)["results"]["bindings"][0]
    return res["table_path"]["value"]


def get_table_info(config, dataset, table, show_query):
    query = PREFIXES + """
    SELECT (max(?rows) as ?number_of_rows) (COUNT(?col) as ?number_of_columns) 
	WHERE
	{
      ?dataset	schema:name				"%s"	;
      			rdf:type				sack:Dataset	.
      ?table	schema:name				"%s"	;
      			rdf:type				sack:Table	;
      			data:hasFilePath		?table_path		.
      ?col		sack:isPartOf			?table			;	
                rdf:type				sack:Column	;
      			data:hasTotalValueCount	?rows			.   			
    } 
    """ % (dataset, table)
    if show_query:
        print(query)
    res = query_graphdb(config, query)["results"]["bindings"][0]
    rows = res["number_of_rows"]["value"]
    columns = res["number_of_columns"]["value"]

    return pd.DataFrame(
        {'Dataset': [dataset], 'Table': [table], 'Path_to_table':
            [get_table_path(config, dataset, table)], 'Number_of_columns': [columns],
         'Number_of_rows': [rows]})


def _create_tables_df_row(results):
    return {
        'Dataset': results['dataset_name']['value'],
        'Table': results['name']['value'],
        'Number_of_columns': float(results['number_of_columns']['value']),
        'Number_of_rows': float(results['number_of_rows']['value']),
        'Path_to_table': results['path']['value']
    }


def search_tables_on(config, all_conditions: tuple, show_query: bool):
    def search(conditions: tuple):
        return PREFIXES + \
            '\nselect ?name ?dataset_name ?path (' \
            'count(distinct ?cols) as ?number_of_columns) (max (?total) as ?number_of_rows)' \
            '\nwhere {' \
            '\n?table schema:name ?name.' \
            '\n?table data:hasFilePath ?path.' \
            '\n?table sack:isPartOf ?dataset.' \
            '\n?dataset schema:name ?dataset_name.' \
            '\n?cols sack:isPartOf ?table.' \
            '\n?cols data:hasTotalValueCount ?total.\n' \
            + conditions[0] + \
            '\nfilter( ' + conditions[1] + ')}' \
                                           '\n group by ?name ?dataset_name ?path'

    query = search(all_conditions)
    if show_query:
        print(query)
    res = query_graphdb(config, query, return_type='json')

    for result in res:
        yield _create_tables_df_row(result)


def _get_iri(config, dataset_name: str, table_name: str = None, show_query: bool = False):
    if table_name is None:
        query = PREFIXES + \
                '\nselect ?id' \
                '\nwhere {' \
                '\n?id a sack:Dataset.' \
                '\n?id rdfs:label %s }' % dataset_name
    else:
        query = PREFIXES + \
                '\nselect ?id where{' \
                '\n?id a sack:Table.' \
                '\n?id rdfs:label %s.' \
                '\n?id sack:isPartOf ?dataset.' \
                '\n?dataset rdfs:label %s.' \
                '\n?dataset a sack:Dataset.}' % (table_name, dataset_name)
    if show_query:
        print(query)
    results = query_graphdb(config, query, return_type='json')
    bindings = results
    if not bindings:
        return None
    return str(bindings[0]['id']['value'])


def get_iri_of_table(config, dataset_name: str, table_name: str, show_query: bool = False):
    dataset_label = generate_label(dataset_name, 'en')
    table_label = generate_label(table_name, 'en')
    return _get_iri(config, dataset_label, table_label, show_query)


def generate_label(col_name: str, lan: str) -> Label:
    if '.csv' in col_name:
        col_name = re.sub('.csv', '', col_name)
    col_name = re.sub('[^0-9a-zA-Z]+', ' ', col_name)
    text = " ".join(camelsplit(col_name.strip()))
    text = re.sub(r'\s+', ' ', text.strip())
    return Label(text.lower(), lan)


def _create_path_row(result, hops):
    data = {'starting_column': result['c1name']['value'],
            'starting_table': result['t1name']['value'],
            'starting_table_path': result['t1path']['value'],
            'starting_dataset': result['d1name']['value']}

    intermediate = {}
    for i in range(2, hops + 1):
        intermediate.update({'intermediate_column_land_in' + str(i): result['c' + str(i) + 'name']['value'],
                             'intermediate_table' + str(i): result['t' + str(i) + 'name']['value'],
                             'intermediate_table_path' + str(i): result['t' + str(i) + 'path']['value'],
                             'intermediate_column_take_off' + str(i): result['cc' + str(i) + 'name']['value'],
                             'intermediate_dataset' + str(i): result['d' + str(i) + 'name']['value']})
    data.update(intermediate)

    data.update({'target_column': result['c' + str(hops + 1) + 'name']['value'],
                 'target_table': result['t' + str(hops + 1) + 'name']['value'],
                 'target_table_path': result['t' + str(hops + 1) + 'path']['value'],
                 'target_dataset': result['d' + str(hops + 1) + 'name']['value']})
    return data


def get_path_between(config, start_iri: str, target_iri: str, predicate: str, hops: int,
                     show_query: bool = False):
    def _generate_starting_nodes() -> str:
        return '\n    ?c1 schema:name ?c1name.' \
               '\n    ?c1 sack:isPartOf ?t1.' \
               '\n    ?t1 schema:name ?t1name.' \
               '\n    ?t1 data:hasFilePath ?t1path.' \
               '\n    ?t1 sack:isPartOf ?d1.' \
               '\n    ?d1 schema:name ?d1name.'

    def _generate_intermediate_nodes(h: int) -> str:
        inters = ''
        for i in range(2, h + 1):
            inter = '\n    ?c' + str(i) + ' a sack:Column.' \
                                          '\n    ?c' + str(i) + ' schema:name ?c' + str(i) + 'name.' \
                                                                                             '\n    ?c' + str(
                i) + ' sack:isPartOf ?t' + str(i) + '.' \
                                                      '\n    ?t' + str(i) + ' schema:name ?t' + str(i) + 'name.' \
                                                                                                         '\n    ?t' + str(
                i) + ' data:hasFilePath ?t' + str(i) + 'path.' \
                                                       '\n    ?cc' + str(i) + ' sack:isPartOf ?t' + str(i) + '.' \
                                                                                                               '\n    ?cc' + str(
                i) + ' schema:name ?cc' + str(i) + 'name.' \
                                                   '\n    ?t' + str(i) + ' sack:isPartOf ?d' + str(i) + '.' \
                                                                                                          '\n    ?d' + str(
                i) + ' schema:name ?d' + str(i) + 'name.'
            inters += inter
        return inters

    def _generate_target_nodes(h: int) -> str:
        return '\n    ?c' + str(h + 1) + ' schema:name ?c' + str(h + 1) + 'name.' \
                                                                          '\n    ?c' + str(
            h + 1) + ' sack:isPartOf ?t' + str(h + 1) + '.' \
                                                          '\n    ?t' + str(h + 1) + ' schema:name ?t' + str(
            h + 1) + 'name.' \
                     '\n    ?t' + str(h + 1) + ' data:hasFilePath ?t' + str(h + 1) + 'path.' \
                                                                                     '\n    ?t' + str(
            h + 1) + ' sack:isPartOf ?d' + str(h + 1) + '.' \
                                                          '\n    ?d' + str(h + 1) + ' schema:name ?d' + str(
            h + 1) + 'name.'

    def _generate_relationships(h: int, pred: str) -> str:
        relations = '\n    << ?c1 ' + pred + ' ?c2 >> data:withCertainty	?certainty1'
        for i in range(2, h + 1):
            relation = f'\n     << ?cc{i} {pred} ?c{i + 1}>> data:withCertainty	?certainty{i}.'
            relations += relation
        return relations

    def _generate_select(h: int) -> str:
        selects = '\n ?c1name ?t1name ?t1path ?d1name'
        for i in range(2, h + 1):
            selects += '\n ?c' + str(i) + 'name ?t' + str(i) + 'name ?t' + str(i) + 'path' \
                                                                                    ' ?cc' + str(i) + 'name ?d' + str(
                i) + 'name'
        selects += '\n ?c' + str(h + 1) + 'name ?t' + str(h + 1) + 'name ?t' + str(h + 1) + 'path ?d' + str(
            h + 1) + 'name'
        return selects

    starting_nodes = _generate_starting_nodes()
    intermediate_nodes = _generate_intermediate_nodes(hops)
    target_nodes = _generate_target_nodes(hops)
    relationships = _generate_relationships(hops, predicate)
    select = _generate_select(hops)
    all_nodes = starting_nodes + intermediate_nodes + target_nodes

    query = PREFIXES + \
            '\n select' + select + \
            '\nwhere {' + \
            all_nodes + relationships + \
            '\n values ?t1 {' + start_iri + '}' + \
            '\n values ?t' + str(hops + 1) + ' {' + target_iri + '}}'

    if show_query:
        print(query)
    results = query_graphdb(config, query, return_type='json')
    bindings = results
    if not bindings:
        return []
    for result in bindings:
        yield _create_path_row(result, hops)


def generate_component_id(dataset_name: str, table_name: str = '', column_name: str = ''):
    return zlib.crc32(bytes(dataset_name + table_name + column_name, 'utf-8'))


def generate_graphviz(df: pd.DataFrame, predicate: str):
    def parse_starting_or_target_nodes(dot, row, column_ids: list, table_ids: list, dataset_ids: list,
                                       start: bool) -> str:
        relation_name = 'partOf'
        if start:
            dataset_name = row[0]
            table_name = row[1]
            column_name = row[3]
            color = 'lightblue2'
        else:
            dataset_name = row[-4]
            table_name = row[-3]
            column_name = row[-1]
            color = 'darkorange3'
        dataset_id = str(generate_component_id(dataset_name))
        table_id = str(generate_component_id(dataset_name, table_name))
        column_id = str(generate_component_id(dataset_name, table_name, column_name))
        if column_id in column_ids:
            return column_id
        dot.node(column_id, column_name, style='filled', fillcolor=color)
        column_ids.append(column_id)
        if table_id in table_ids:
            dot.edge(column_id, table_id, relation_name)
            return column_id
        dot.node(table_id, table_name, style='filled', fillcolor=color)
        table_ids.append(table_id)
        if dataset_id in dataset_ids:
            dot.edge(column_id, table_id, relation_name)
            dot.edge(table_id, dataset_id, relation_name)
            return column_id
        dot.node(dataset_id, dataset_name, style='filled', fillcolor=color)
        dataset_ids.append(dataset_id)
        dot.edge(column_id, table_id, relation_name)
        dot.edge(table_id, dataset_id, relation_name)
        return column_id

    def parse_intermediate_nodes(dot, row, column_ids: list, table_ids: list, dataset_ids: list) -> list:
        ids = []
        relation_name = 'partOf'
        for i in range(4, len(row) - 4, 5):
            dataset_name = row[i]
            table_name = row[i + 1]
            land_in_column_name = row[i + 2]
            take_off_column_name = row[i + 4]
            dataset_id = str(generate_component_id(dataset_name))
            table_id = str(generate_component_id(dataset_name, table_name))
            land_in_column_id = str(generate_component_id(dataset_name, table_name, land_in_column_name))
            take_off_column_id = str(generate_component_id(dataset_name, table_name, take_off_column_name))
            ids.extend([land_in_column_id, take_off_column_id])

            land_in_column_exist = False
            take_off_column_exist = False
            if land_in_column_id in column_ids:
                land_in_column_exist = True
            dot.node(land_in_column_id, land_in_column_name)
            column_ids.append(land_in_column_id)

            if take_off_column_id in column_ids:
                take_off_column_exist = True

            if land_in_column_exist and take_off_column_exist:
                continue
            dot.node(take_off_column_id, take_off_column_name)
            column_ids.append(take_off_column_id)

            if table_id in table_ids:
                if land_in_column_id == take_off_column_id:
                    dot.edge(land_in_column_id, table_id, relation_name)
                else:
                    dot.edge(land_in_column_id, table_id, relation_name)
                    dot.edge(take_off_column_id, table_id, relation_name)
                continue

            dot.node(table_id, table_name)
            table_ids.append(table_id)
            if dataset_id in dataset_ids:
                if land_in_column_id == take_off_column_id:
                    dot.edge(land_in_column_id, table_id, relation_name)
                else:
                    dot.edge(land_in_column_id, table_id, relation_name)
                    dot.edge(take_off_column_id, table_id, relation_name)
                dot.edge(table_id, dataset_id, relation_name)
                continue
            dot.node(dataset_id, dataset_name)
            dataset_ids.append(dataset_id)
            if land_in_column_id == take_off_column_id:
                dot.edge(land_in_column_id, table_id, relation_name)
            else:
                dot.edge(land_in_column_id, table_id, relation_name)
                dot.edge(take_off_column_id, table_id, relation_name)
            dot.edge(table_id, dataset_id, relation_name)
        return ids

    def establish_relationships(dot, row_ids: list, relationships: list):

        for j in range(0, len(row_ids) - 1, 2):
            pair = (row_ids[j], row_ids[j + 1])
            if pair[0] == pair[1]:
                continue
            if not pair in relationships:
                relationships.append(pair)
                dot.edge(pair[0], pair[1], 'similar', dir='none')

    col_ids = []
    tab_ids = []
    data_ids = []
    relations = []
    dot_graph = Digraph(strict=True)
    for i in range(len(df)):
        r = df.iloc[i]
        row_col_ids = []
        starting_column_id = parse_starting_or_target_nodes(dot_graph, r, col_ids, tab_ids, data_ids, True)
        intermediate_col_ids = parse_intermediate_nodes(dot_graph, r, col_ids, tab_ids, data_ids)
        target_col_id = parse_starting_or_target_nodes(dot_graph, r, col_ids, tab_ids, data_ids, False)

        row_col_ids.append(starting_column_id)
        row_col_ids.extend(intermediate_col_ids)
        row_col_ids.append(target_col_id)

        establish_relationships(dot_graph, row_col_ids, relations)
    dot_graph.attr(label='Paths between starting nodes in blue and target nodes in orange')

    return dot_graph


def get_path_between_tables(config, source_table_info, target_table_info, hops, relation, show_query):
    source_table_name = source_table_info["Table"]
    source_dataset_name = source_table_info["Dataset"]
    target_dataset_name = target_table_info["Dataset"]
    if 'Recommended_table' in target_table_info.keys():
        target_table_name = target_table_info["Recommended_table"]
    else:
        target_table_name = target_table_info["Table"]

    starting_table_iri = get_iri_of_table(config,
                                          dataset_name=generate_label(source_dataset_name, 'en').get_text(),
                                          table_name=generate_label(source_table_name, 'en').get_text())
    target_table_iri = get_iri_of_table(config,
                                        dataset_name=generate_label(target_dataset_name, 'en').get_text(),
                                        table_name=generate_label(target_table_name, 'en').get_text())

    if starting_table_iri is None:
        raise ValueError(str(source_table_info) + ' does not exist')
    if target_table_iri is None:
        raise ValueError(str(target_table_info) + ' does not exist')

    data = get_path_between(config, '<' + starting_table_iri + '>', '<' + target_table_iri + '>',
                            relation, hops, show_query)

    path_row = ['starting_dataset', 'starting_table', 'starting_table_path', 'starting_column']
    for i in range(2, hops + 1):
        intermediate = ['intermediate_dataset' + str(i), 'intermediate_table' + str(i),
                        'intermediate_column_land_in' + str(i), 'intermediate_table_path' + str(i),
                        'intermediate_column_take_off' + str(i)]
        path_row.extend(intermediate)
    path_row.extend(['target_dataset', 'target_table', 'target_table_path', 'target_column'])
    df = pd.DataFrame(list(data), columns=path_row)
    dot = generate_graphviz(df, relation)
    return dot


def get_top_scoring_ml_model(config, dataset, show_query):
    query = """
    PREFIX sack: <http://sack.local/ontology/>
    SELECT (count(?x) as ?count)
    WHERE
    {
        ?x rdf:type sack:Pipeline .
    }
    """
    return query_graphdb(config, query)


def get_pipelines_info(config, author, show_query):
    if author != '':
        author = "FILTER (?Author = '{}')   .".format(author)

    query = PREFIXES + """
    SELECT ?Pipeline ?Dataset ?Author ?Written_on ?Number_of_votes ?Score
    WHERE
    {
        ?pipeline_id    rdf:type                sack:Pipeline     ;
                        pipeline:hasVotes       ?Number_of_votes    ;
                        rdfs:label              ?Pipeline           ;
                        pipeline:isWrittenOn    ?Written_on         ;
                        pipeline:isWrittenBy    ?Author             ;
                        pipeline:hasScore       ?Score              ;
                        sack:isPartOf         ?Dataset_id         .
        ?Dataset_id     schema:name             ?Dataset            .
        %s
    } ORDER BY DESC(?Number_of_votes) 
    """ % author
    if show_query:
        print(query)

    return query_graphdb(config, query)


def get_most_recent_pipeline(config, dataset, show_query):
    if dataset != '':
        dataset = "FILTER (?Dataset = '{}')     .".format(dataset)

    query = PREFIXES + """
    SELECT ?Pipeline ?Dataset ?Author ?Written_on ?Number_of_votes ?Score
    WHERE
    {
        ?pipeline_id    rdf:type                sack:Pipeline     ;
                        pipeline:hasVotes       ?Number_of_votes    ;
                        rdfs:label              ?Pipeline           ;
                        pipeline:isWrittenOn    ?Written_on         ;  # 创建时间
                        pipeline:isWrittenBy    ?Author             ;
                        pipeline:hasScore       ?Score              ;
                        sack:isPartOf         ?Dataset_id         .
        ?Dataset_id     schema:name             ?Dataset            .
        %s                          
    } ORDER BY DESC(?Written_on) LIMIT 1
    """ % dataset
    if show_query:
        print(query)
    return query_graphdb(config, query)


def get_top_k_scoring_pipelines_for_dataset(
        config,
        competition_uri: str,  # 改为竞赛URI（如http://sack.local/resource/kaggle/playground-series-s3e23）
        k: int = None,
        show_query: bool = False
):
    """
    根据竞赛URI检索关联的Top K评分pipeline（竞赛与dataset为同一概念，均为sack:Dataset类型）

    参数:
        config: 包含graphdb连接信息的配置字典
        competition_uri: 竞赛的URI（sack:Dataset实体的唯一标识）
        k: 返回的pipeline数量（None则返回全部）
        show_query: 是否打印SPARQL查询语句
    """
    # 处理返回数量限制（LIMIT子句）
    limit_clause = f'LIMIT {k}' if k is not None else ''

    # 处理竞赛URI过滤条件（精确匹配sack:Dataset实体的URI）
    if competition_uri:
        # 通过?Dataset_id（即竞赛URI）过滤，因?pipeline:isPartOf关联到竞赛实体
        filter_clause = f"FILTER (?Dataset_id = <{competition_uri}>) ."
    else:
        filter_clause = ""  # 为空时不过滤，返回所有竞赛的pipeline

    # 构建SPARQL查询（核心：通过竞赛URI匹配关联的pipeline）
    query = PREFIXES + f"""
    SELECT ?Pipeline_id ?Pipeline ?Author ?Written_on ?Number_of_votes ?Score
    WHERE {{
        ?Pipeline_id    rdf:type                sack:Pipeline     ;
                        pipeline:hasVotes       ?Number_of_votes    ;
                        rdfs:label              ?Pipeline           ;  # pipeline名称
                        pipeline:isWrittenOn    ?Written_on         ;  # 创建时间
                        pipeline:isWrittenBy    ?Author             ;  # 作者
                        pipeline:hasScore       ?Score              ;  # 评分
                        sack:isPartOf         ?Dataset_id         .  # 关联到竞赛实体（?Dataset_id即竞赛URI）

        ?Dataset_id     a                       sack:Dataset      .  # 明确类型为竞赛（dataset）

        {filter_clause}  # 按竞赛URI过滤
    }} 
    ORDER BY DESC(?Score)  # 按评分降序排列
    {limit_clause}  # 限制返回数量
    """

    if show_query:
        print("=" * 60)
        print(f"【Top K评分pipeline查询】SPARQL语句：")
        print(query)
        print("=" * 60)

    # 执行查询并返回结果
    return query_graphdb(config, query)


CLASSIFIERS = {'RandomForestClassifier': '<http://sack.local/resource/library/sklearn/ensemble/RandomForestClassifier>',
               'SVC': '<http://sack.local/resource/library/sklearn/svm/SVC>',
               'KNeighborsClassifier': '<http:/sack.local/resource/library/sklearn/neighbors/KNeighborsClassifier>',
               'GradientBoostingClassifier': '<http://sack.local/resource/library/sklearn/ensemble/GradientBoostingClassifier>',
               'LogisticRegression': '<http://sack.local/resource/library/sklearn/linear_model/LogisticRegression>',
               'DecisionTreeClassifier': '<http://sack.local/resource/library/sklearn/tree/DecisionTreeClassifier>',
               'AdaBoostClassifier': '<http://sack.local/resource/library/sklearn/ensemble/AdaBoostClassifier>',
               'SGDClassifier': '<http://sack.local/resource/library/sklearn/linear_model/SGDClassifier>',
               'MLPClassifier': '<http://sack.local/resource/library/sklearn/neural_network/MLPClassifier>',
               'XGBClassifier': '<http://sack.local/resource/library/xgboost/XGBClassifier>',
               'VotingClassifier': '<http://sack.local/resource/library/sklearn/ensemble/VotingClassifier>',
               'PassiveAggressiveClassifier': '<http://sack.local/resource/library/sklearn/linear_model/PassiveAggressiveClassifier>',
               'BaggingClassifier': '<http://sack.local/resource/library/sklearn/ensemble/BaggingClassifier>',
               'RidgeClassifier': '<http://sack.local/resource/library/sklearn/linear_model/RidgeClassifier>',
               'RadiusNeighborsClassifier': '<http://sack.local/resource/library/sklearn/neighbors/RadiusNeighborsClassifier>',
               'ExtraTreesClassifier': '<http://sack.local/resource/library/sklearn/ensemble/ExtraTreesClassifier>',
               'TFDistilBertForSequenceClassification': '<http://sack.local/resource/library/transformers/TFDistilBertForSequenceClassification>'}


def search_classifier(config, dataset, show_query):
    sub_graph_query = """
    """
    for classifier, classifier_url in CLASSIFIERS.items():
        if classifier != 'RandomForestClassifier':
            query = """
            UNION
                     {
                        ?Statement_number    pipeline:callsClass %s.
                        BIND('%s' as ?Classifier)
                     }
            """ % (classifier_url, classifier)
            sub_graph_query = sub_graph_query + query

    filter_for_dataset = ''
    if dataset != '':
        filter_for_dataset = '?Dataset_id    schema:name "{}".'.format(dataset)

    query = PREFIXES + """
    SELECT DISTINCT ?Dataset ?Pipeline ?Classifier ?Score
    WHERE 
    {
        ?Dataset_id     rdf:type          sack:Dataset ;
                        schema:name       ?Dataset       .
        ?Pipeline_id    sack:isPartOf   ?Dataset_id    ;
                        rdfs:label        ?Pipeline      ;
                        pipeline:hasScore ?Score         .
       graph ?Pipeline_id 
         {
            ?x pipeline:callsClass ?y
             {
                ?Statement_number    pipeline:callsClass <http://sack.local/resource/library/sklearn/ensemble/RandomForestClassifier>  .
                BIND('RandomForestClassifier' as ?Classifier)
             }""" + sub_graph_query + """

         }
    %s
    } ORDER BY DESC(?Score) """ % filter_for_dataset

    if show_query:
        print(query)

    return query_graphdb(config, query)


def get_hyperparameters(config, pipeline, classifier, show_query):
    classifier_url = CLASSIFIERS.get(classifier)
    parameter_heading = '?{}_hyperparameter'.format(classifier)
    query = PREFIXES + """

    SELECT DISTINCT %s ?Value
        WHERE
        {
            ?Pipeline_id    rdfs:label        '%s'     ;
                            pipeline:hasScore ?Score         .
           graph ?Pipeline_id
             {
                 ?Statement_number    pipeline:callsClass   %s .
                 << ?Statement_number pipeline:hasParameter %s >> pipeline:withParameterValue ?Value  .
             }
        } ORDER BY DESC(?Score)""" % (parameter_heading, pipeline, classifier_url, parameter_heading)

    if show_query:
        print(query)

    df = query_graphdb(config, query)
    if np.shape(df)[0] == 0:
        return 'Using default configurations'
    else:
        return df


def get_library_usage(config, dataset, k, show_query):
    if dataset != '':
        dataset = '?Dataset    schema:name        "{}"        .\n\t\t' \
                  '?Pipeline   sack:isPartOf    ?Dataset  .'.format(dataset)
    query = PREFIXES + """
    SELECT ?Library (COUNT(distinct ?Pipeline) as ?Usage)
    WHERE
    {
        %s
        ?Pipeline   rdf:type    sack:Pipeline                 .
        GRAPH ?Pipeline
        {
            ?Statement pipeline:callsClass ?l                 .
            BIND(STRAFTER(str(?l), str(lib:)) as ?l1)      .
            BIND(STRBEFORE(str(?l1), str('/')) as ?Library)     .
        }
        FILTER (?Library != "")              .
        FILTER (?Library != "builtin")       .         
    } GROUP BY ?Library ORDER BY DESC(?Usage)
    """ % dataset
    if show_query:
        print(query)
    df = query_graphdb(config, query)
    df['Usage (in %)'] = list(map(lambda x: x * 100, [int(i) / sum(df['Usage'].
                                                                   tolist()) for i in (df['Usage'].tolist())]))
    if len(df) == 0:
        print("No library found")
        return

    df = df.head(k)
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.bar(range(len(df)), df['Usage'].tolist(), color='mediumseagreen')
    ax.set_xticks(range(len(df)))
    ax.set_xticklabels(df['Library'].tolist(), rotation=20)
    ax.set_ylabel('Number of Pipelines')
    for i, usage in enumerate(df['Usage']):
        ax.text(i - 0.35, usage + int(0.05 * usage), str(usage), color='k', fontweight='bold')
    ax.set_ylim(0, df['Usage'].max() + int(0.1 * df['Usage'].max()))
    plt.grid(axis='y')
    plt.tight_layout()
    plt.savefig('library_usage_stats.pdf')
    plt.show()


def get_top_used_libraries(config, task, show_query):
    if task == 'classification':
        task = 'classifi'
    elif task == 'clustering':
        task = 'cluster'
    elif task == 'visualization':
        task = 'plot'
    else:
        task = 'regress'
    query = PREFIXES + """
    SELECT DISTINCT ?Library ?Module ?Pipeline ?Dataset 
    WHERE
    {
        ?Pipeline_id    rdf:type                    sack:Pipeline         ;
                        rdfs:label                  ?Pipeline               ;
                        sack:isPartOf             ?dataset_id             .

        ?dataset_id     schema:name                 ?Dataset                .

        GRAPH ?Pipeline_id
        {
            ?statement  pipeline:callsFunction    ?l                         .
            BIND(STRAFTER(str(?l), str(lib:)) as ?l1)                       .
            BIND(STRBEFORE(str(?l1), str('/')) as ?Library)                 .  
            BIND (REPLACE(STR(?l), "^.*/([^/]*)/([^/]*)$", "$1") as ?Module)        .    
        }    

        FILTER(regex(str(?l), "%s", "i"))             
    }""" % task
    if show_query:
        print(query)

    return query_graphdb(config, query)


def get_pipelines_calling_libraries(config, components, show_query):
    sub_query = ''
    for i in range(len(components)):
        # check if class or function (classes start with an upper case letter (heuristic))
        if components[i].split('.')[-1][0].isupper():
            predicate = 'pipeline:callsClass'
        else:
            predicate = 'pipeline:callsFunction'
        sub_query = sub_query + \
                    '?Statement_{}   {}   <http://sack.local/resource/library/{}> .\n        ' \
                        .format(i + 1, predicate, components[i].replace('.', '/'))

    query = PREFIXES + """
    SELECT DISTINCT ?Pipeline ?Dataset ?Author ?Score ?Number_of_votes
    WHERE 
    {

        ?Pipeline_id    rdf:type                sack:Pipeline     ;
                        pipeline:hasVotes       ?Number_of_votes    ;
                        rdfs:label              ?Pipeline           ;
                        pipeline:isWrittenOn    ?Written_on         ;
                        pipeline:isWrittenBy    ?Author             ;
                        pipeline:hasScore       ?Score              ;
                        sack:isPartOf         ?Dataset_id         ;

        graph ?Pipeline_id
        {
        %s
        }  
        ?Dataset_id     schema:name             ?Dataset            . 
    } ORDER BY DESC(?Score)""" % sub_query
    if show_query:
        print(query)

    return query_graphdb(config, query)


def get_pipelines_for_deep_learning(config, show_query):
    query = PREFIXES + """
    SELECT DISTINCT ?Pipeline ?Dataset ?Author ?Written_on ?Score ?Number_of_votes
    WHERE 
    {
    ?Pipeline_id    rdf:type                sack:Pipeline     ;
                    pipeline:hasVotes       ?Number_of_votes    ;
                    rdfs:label              ?Pipeline           ;
                    pipeline:isWrittenOn    ?Written_on         ;
                    pipeline:isWrittenBy    ?Author             ;
                    pipeline:hasScore       ?Score              ;
                    pipeline:hasTag         ?Tag                ;
                    sack:isPartOf         ?Dataset_id         .

    ?Dataset_id     schema:name             ?Dataset            . 

    FILTER(regex(?Tag, "deep learning", "i")) 
    } ORDER BY DESC(?Score)"""
    if show_query:
        print(query)

    return query_graphdb(config, query)


def recommend_transformations(config, show_query):
    query = PREFIXES + """
    SELECT DISTINCT ?Transformation ?Pipeline (?Table_id as ?Table) ?Dataset 
    WHERE
    {
    ?Pipeline_id    rdf:type                sack:Pipeline     ;
                    rdfs:label              ?Pipeline           ;
                    sack:isPartOf         ?Dataset_id         .

    ?Dataset_id     schema:name             ?Dataset            . 

    graph ?Pipeline_id
    {   
        ?s          pipeline:callsClass    ?l                 . 
        BIND(STRAFTER(str(?l), str(lib:)) as ?Transformation)   . 
        ?Table_id   rdf:type                 sack:Table       . 

    }
    FILTER(regex(str(?l), "preprocessing", "i"))
    } ORDER BY DESC(?Score) """

    if show_query:
        print(query)

    df = query_graphdb(config, query)
    df['Table'] = df['Table'].apply(lambda x: x.rsplit('/', 1)[-1])
    df['Transformation'] = df['Transformation'].apply(lambda x: x.replace('/', '.'))
    return df


def get_pipelines_by_tags(config, tag, show_query):
    if tag != '':
        tag = 'FILTER(regex(?Tag, "{}", "i"))'.format(tag)
    query = PREFIXES + """
    SELECT DISTINCT ?Tag (COUNT (?Pipeline_id) AS ?Number_of_pipelines) 
    WHERE
    {
    ?Pipeline_id    rdf:type                sack:Pipeline     ;
                    pipeline:hasTag         ?Tag                .
    %s
    } GROUP BY ?Tag ORDER BY DESC(?Number_of_pipelines)
    """ % tag
    if show_query:
        print(query)
    return query_graphdb(config, query)


def plot_top_k_classifiers(config, k, show_query):
    query = PREFIXES + """
    SELECT DISTINCT ?Module (COUNT (?Module) as ?Usage)
    WHERE
    {
    ?Pipeline_id    rdf:type                    sack:Pipeline         ;
                    rdfs:label                  ?Pipeline               ;
                    sack:isPartOf             ?dataset_id             .

    ?dataset_id     schema:name                 ?Dataset                .

    GRAPH ?Pipeline_id
    {
        ?statement  pipeline:callsFunction    ?l                         .
        BIND(STRAFTER(str(?l), str(lib:)) as ?l1)                       .
        BIND(STRBEFORE(str(?l1), str('/')) as ?Library)                 .  
        BIND (REPLACE(STR(?l), "^.*/([^/]*)/([^/]*)$", "$1") as ?Module)                  .  
    }    

    FILTER(regex(str(?l), "classifier", "i"))
    FILTER (!regex(str(?l), "report", "i"))
    FILTER (!regex(str(?l), "ROCAUC", "i"))  
    FILTER (!regex(str(?l), "threshold", "i"))  
    } GROUP BY ?Module ORDER BY DESC(?Usage)"""

    if show_query:
        print(query)
    df = query_graphdb(config, query)
    df['Usage (in %)'] = list(map(lambda x: x * 100, [int(i) / sum(df['Usage'].
                                                                   tolist()) for i in (df['Usage'].tolist())]))

    df['Classifier'] = df['Module'].apply(lambda x: x.rsplit('/', 1)[-1])

    if len(df) == 0:
        print("No classifier found")
        return
    if len(df) < k:
        print('Maximum {} classifier(s) were found'.format(len(df)))
        print('Showing top-{} classifiers'.format(len(df)))
        k = len(df)
    df = df.head(k)
    plt.rcParams['figure.figsize'] = 10, 5
    plt.rcParams['figure.dpi'] = 300
    plt.rcParams['savefig.dpi'] = 300
    sns.set_theme(style='darkgrid')
    ax = sns.barplot(x="Classifier", y="Usage (in %)", data=df, palette='viridis')
    ax = ax.set_xticklabels(ax.get_xticklabels(), rotation=40)


def plot_top_k_regressors(config, k, show_query):
    query = PREFIXES + """
    SELECT DISTINCT ?Module (COUNT (?Module) as ?Usage)
    WHERE
    {
    ?Pipeline_id    rdf:type                    sack:Pipeline         ;
                    rdfs:label                  ?Pipeline               ;
                    sack:isPartOf             ?dataset_id             .

    ?dataset_id     schema:name                 ?Dataset                .

    GRAPH ?Pipeline_id
    {
        ?statement  pipeline:callsFunction    ?l                         .
        BIND(STRAFTER(str(?l), str(lib:)) as ?l1)                       .
        BIND(STRBEFORE(str(?l1), str('/')) as ?Library)                 .  
        BIND (REPLACE(STR(?l), "^.*/([^/]*)/([^/]*)$", "$1") as ?Module)                    .  
    }    

    FILTER(regex(str(?l), "regres", "i"))
    } GROUP BY ?Module ORDER BY DESC(?Usage)"""

    if show_query:
        print(query)

    df = query_graphdb(config, query)
    df['Usage (in %)'] = list(map(lambda x: x * 100, [int(i) / sum(df['Usage'].
                                                                   tolist()) for i in (df['Usage'].tolist())]))

    df['Regressor'] = df['Module'].apply(lambda x: x.rsplit('/', 1)[-1])

    if len(df) == 0:
        print("No classifier found")
        return
    if len(df) < k:
        print('Maximum {} regressor(s) were found'.format(len(df)))
        print('Showing top-{} regressors'.format(len(df)))
        k = len(df)
    df = df.head(k)
    plt.rcParams['figure.figsize'] = 10, 5
    plt.rcParams['figure.dpi'] = 300
    plt.rcParams['savefig.dpi'] = 300
    sns.set_theme(style='darkgrid')
    ax = sns.barplot(x="Regressor", y="Usage (in %)", data=df, palette='viridis')
    ax = ax.set_xticklabels(ax.get_xticklabels(), rotation=40)


# 全局类型兼容规则（核心逻辑内定义，与相似度计算强关联）
TYPE_COMPATIBILITY = {
    "int": ["int", "float"],  # ColumnDataType.INT.value
    "float": ["int", "float"],  # ColumnDataType.FLOAT.value
    "string": ["string", "named_entity", "natural_language_text"],  # ColumnDataType.STRING.value
    "named_entity": ["string", "named_entity", "natural_language_text"],
    # ColumnDataType.NATURAL_LANGUAGE_NAMED_ENTITY.value
    "natural_language_text": ["string", "named_entity", "natural_language_text"],
    # ColumnDataType.NATURAL_LANGUAGE_TEXT.value
    "boolean": ["boolean"],  # ColumnDataType.BOOLEAN.value
    "date": ["date"]  # ColumnDataType.DATE.value
}


def filter_candidate_competitions(config: dict, current_problem_type: str, current_data_type: str, current_comp_id: str,
                                  show_query: bool = False) -> list:
    # 1. 补全当前竞赛的完整URI（对齐图谱中的comp_uri格式）
    # 图谱中comp_uri是“http://sack.local/resource/xxx”，current_comp_id是“kaggle/playground-series-s3e8”
    full_current_comp_uri = f"http://sack.local/resource/{current_comp_id}"

    graph_store = _configured_graph_store(config)
    if graph_store is not None:
        return graph_store.find_candidate_competitions(
            current_problem_type,
            current_data_type,
            full_current_comp_uri,
        )

    graphdb_conn = config["graphdb_conn"]

    # 2. 修复：用全局PREFIXES，不重复声明前缀，谓词用data:
    sparql_query = PREFIXES + f"""
    SELECT DISTINCT ?comp_uri
    WHERE {{
        ?comp_uri a sack:Dataset ;
                  data:hasProblemType "{current_problem_type}" ;  # 对齐data:前缀
                  data:hasDataType "{current_data_type}" .       # 对齐data:前缀
        FILTER (?comp_uri != <{full_current_comp_uri}>)  # 排除当前竞赛（用完整URI）
    }}
    """
    if show_query:
        print(f"\n【初筛SPARQL】：\n{sparql_query}")

    results = query_graphdb(graphdb_conn, sparql_query, return_type='json')
    return [res["comp_uri"]["value"] for res in results] if results else []


def query_postgres_competition_semantic(
        config: dict,
        emb: list,  # 改为接收列表
        current_comp_id: str,
        emb_col: str = "overview_embedding",
        show_query: bool = False
) -> Dict[str, float]:
    # 1. 获取竞赛数据库连接（不变）
    pg_conn = config["pg_competition_conn"]
    competition_table_name = config.get("pg_competition_table", SACKKnowledgeConfig.competition_embeddings_db_name)

    # 2. 构造SQL（不变，占位符仍用%s）
    query = f"""
    SELECT 
        competition_id,
        1 - ({emb_col} <-> %s::vector(300)) AS similarity_score  -- 明确指定维度300
    FROM {competition_table_name}
    WHERE competition_id != %s
    ORDER BY similarity_score DESC;
    """

    # 3. 关键修复：将向量列表适配为PostgreSQL的vector类型
    params = (emb, current_comp_id)

    if show_query:
        print(f"\n=== template: query_postgres_competition_semantic 查询 ===")
        print(f"SQL: {query}")
        print(f"Params: {params}")

    # 执行PG查询（复用helper函数）
    results = query_postgres(
        pg_conn=pg_conn,
        query=query,
        params=params,
        return_type='json'
    )

    # 处理结果：补全竞赛URI
    score_dict = {}
    for row in results:
        comp_full_id = f'http://sack.local/resource/{row["competition_id"]}'
        score_dict[comp_full_id] = round(float(row["similarity_score"]), 3)
    return score_dict


def query_postgres_competition_data_desc_similarity(
        config: dict,
        emb: list,
        current_comp_id: str,
        show_query: bool = False
) -> Dict[str, float]:
    """
    从PostgreSQL查询竞赛data_description嵌入相似度（宏观数据得分）
    返回：{竞赛URI: 宏观相似度得分}
    """
    pg_conn = config["pg_competition_conn"]
    competition_table_name = config.get("pg_competition_table", SACKKnowledgeConfig.competition_embeddings_db_name)

    # 构造PG查询（针对data_description_embedding字段）
    query = f"""
    SELECT 
        competition_id,
        1 - (data_description_embedding <-> %s::vector(300)) AS data_desc_sim_score  -- 明确维度
    FROM {competition_table_name}
    WHERE competition_id != %s
    ORDER BY data_desc_sim_score DESC;
    """
    params = (emb, current_comp_id)

    if show_query:
        print(f"\n=== template: query_postgres_competition_data_desc_similarity 查询 ===")
        print(f"SQL: {query}")
        print(f"Params: {params}")

    # 执行查询
    results = query_postgres(
        pg_conn=pg_conn,
        query=query,
        params=params,
        return_type='json'
    )

    # 处理结果（补全竞赛URI）
    score_dict = {}
    for row in results:
        comp_full_id = f'http://sack.local/resource/{row["competition_id"]}'
        score_dict[comp_full_id] = round(float(row["data_desc_sim_score"]), 3)
    return score_dict


def clean_col_uri(col_uri: str) -> str:
    """去除col_uri中的http://sack.local/resource/前缀，与表中id格式匹配"""
    prefix = "http://sack.local/resource/"
    if col_uri.startswith(prefix):
        # 保留前缀后的部分（如kaggle/...）
        return col_uri[len(prefix):]
    return col_uri  # 若没有前缀则直接返回


def get_competition_tables(
        config: dict,
        comp_uri: str,
        show_query: bool = False
) -> List[Dict]:
    """
    基于实际三元组关系，查询目标竞赛的所有表及表的列信息（含列嵌入）
    返回：[{
        "table_uri": "http://sack.local/resource/table1",
        "table_name": "user_info",
        "columns": [{
            "col_uri": "http://sack.local/resource/col1",
            "col_name": "age",
            "data_type": "int",
            "label_embedding": [0.1, ...],  # 从PG获取
            "content_embedding": [0.2, ...] # 从PG获取
        }, ...]
    }, ...]
    """
    pg_col_conn = config["pg_col_conn"]
    graph_store = _configured_graph_store(config)
    graph_tables = []
    if graph_store is not None:
        graph_tables = graph_store.get_competition_tables(comp_uri)
    else:
        graphdb_conn = config["graphdb_conn"]
        table_query = PREFIXES + f"""
        SELECT DISTINCT ?table_uri ?table_name
        WHERE {{
            ?table_uri a sack:Table ;
                       <http://sack.local/ontology/isPartOf> ?comp_uri ;
                       schema:name ?table_name .
            ?comp_uri a sack:Dataset .
            VALUES ?comp_uri {{ <{comp_uri}> }}
        }}
        """
        if show_query:
            print(f"\n=== 查询竞赛 {comp_uri} 的表 ===")
            print(table_query)
        table_results = query_graphdb(graphdb_conn, table_query, return_type="json")
        for table_res in table_results or []:
            table_uri = table_res["table_uri"]["value"]
            col_query = PREFIXES + f"""
            SELECT DISTINCT ?col_uri ?col_name ?data_type
            WHERE {{
                ?col_uri a sack:Column ;
                         <http://sack.local/ontology/isPartOf> ?table_uri ;
                         schema:name ?col_name ;
                         <http://sack.local/ontology/data/hasDataType> ?data_type .
                VALUES ?table_uri {{ <{table_uri}> }}
            }}
            """
            col_results = query_graphdb(graphdb_conn, col_query, return_type="json")
            graph_tables.append(
                {
                    "table_uri": table_uri,
                    "table_name": table_res["table_name"]["value"],
                    "columns": [
                        {
                            "col_uri": value["col_uri"]["value"],
                            "col_name": value["col_name"]["value"],
                            "data_type": value["data_type"]["value"],
                        }
                        for value in col_results or []
                    ],
                }
            )

    if not graph_tables:
        print(f"竞赛 {comp_uri} 未查询到表")
        return []

    def parse_embedding(value):
        if isinstance(value, (list, tuple)):
            return list(value)
        if not isinstance(value, str):
            raise ValueError(f"无法解析嵌入类型：{type(value).__name__}")
        parsed = ast.literal_eval(value)
        if not isinstance(parsed, (list, tuple)):
            raise ValueError("嵌入必须是列表")
        return list(parsed)

    competition_tables = []
    for table in graph_tables:
        table_columns = []
        for column in table["columns"]:
            col_uri = column["col_uri"]
            pg_query = f"""
            SELECT label_embedding, content_embedding
            FROM {config.get("pg_column_table", SACKKnowledgeConfig.column_embeddings_db_name)}
            WHERE id = %s;
            """
            col_emb_results = query_postgres(
                pg_conn=pg_col_conn,
                query=pg_query,
                params=(clean_col_uri(col_uri),),
                return_type="json",
            )
            if not col_emb_results:
                print(f"列 {col_uri} 未查询到嵌入，跳过")
                continue
            table_columns.append(
                {
                    **column,
                    "label_embedding": parse_embedding(
                        col_emb_results[0]["label_embedding"]
                    ),
                    "content_embedding": parse_embedding(
                        col_emb_results[0]["content_embedding"]
                    ),
                    "dataset_name": comp_uri.split("/")[-1],
                }
            )
        if table_columns:
            competition_tables.append(
                {
                    "table_uri": table["table_uri"],
                    "table_name": table["table_name"],
                    "columns": table_columns,
                }
            )
    return competition_tables


def calculate_table_pair_similarity(
        config: dict,
        current_table: Dict,  # 当前竞赛的单个表
        target_table: Dict,  # 目标竞赛的单个表
        fasttext_model: fasttext.FastText._FastText,
        show_query: bool = False
) -> float:
    """
    计算两个表（当前表vs目标表）的相似度：表名初筛→列级匹配
    """
    # Step 1: 计算表名相似度（仅作为辅助评分，不用于筛选）
    current_table_name = current_table["table_name"]
    target_table_name = target_table["table_name"]
    table_name_emb1 = fasttext_model.get_sentence_vector(current_table_name.strip())
    table_name_emb2 = fasttext_model.get_sentence_vector(target_table_name.strip())
    # 余弦相似度计算
    table_name_sim = np.dot(table_name_emb1, table_name_emb2) / (
            np.linalg.norm(table_name_emb1) * np.linalg.norm(table_name_emb2))
    table_name_sim = round(max(0, table_name_sim), 3)

    # Step 2: 列级匹配
    col_match_scores = []
    current_columns = current_table["columns"]
    target_columns = target_table["columns"]

    for current_col in current_columns:
        max_col_sim = 0.0  # 初始化当前列的最大匹配得分
        for target_col in target_columns:
            current_col_type = current_col["data_type"]
            target_col_type = target_col["data_type"]

            # 类型兼容判断
            # print(f"当前列类型：{current_col_type}，目标列类型：{target_col_type}，兼容列表：{TYPE_COMPATIBILITY.get(current_col_type, [])}")
            if target_col_type not in TYPE_COMPATIBILITY.get(current_col_type, []):
                if show_query:
                    print(
                        f"      列 {current_col['col_name']}（类型：{current_col_type}）与 {target_col['col_name']}（类型：{target_col_type}）不兼容，跳过")
                continue

            # 计算标签嵌入相似度
            current_label_emb = np.array(current_col.get("label_embedding", []))
            target_label_emb = np.array(target_col.get("label_embedding", []))
            if current_label_emb.size == 0 or target_label_emb.size == 0:
                label_sim = 0.0
            else:
                label_sim = np.dot(current_label_emb, target_label_emb) / (
                        np.linalg.norm(current_label_emb) * np.linalg.norm(target_label_emb))

            # 计算内容嵌入相似度
            current_content_emb = np.array(current_col.get("content_embedding", []))
            target_content_emb = np.array(target_col.get("content_embedding", []))
            if current_content_emb.size == 0 or target_content_emb.size == 0:
                content_sim = 0.0
            else:
                content_sim = np.dot(current_content_emb, target_content_emb) / (
                        np.linalg.norm(current_content_emb) * np.linalg.norm(target_content_emb))

            # 过滤负相似度并计算列总相似度
            label_sim = round(max(0, label_sim), 3)
            content_sim = round(max(0, content_sim), 3)
            col_sim = round(label_sim * 0.4 + content_sim * 0.6, 3)

            if col_sim > max_col_sim:
                max_col_sim = col_sim

        if max_col_sim > 0:
            col_match_scores.append(max_col_sim)

    # Step 3: 表级相似度计算
    if not col_match_scores:
        return 0.0
    col_avg_sim = round(sum(col_match_scores) / len(col_match_scores), 3)
    table_sim = round(col_avg_sim * 0.9 + table_name_sim * 0.1, 3)

    return table_sim


def query_all_competitions_fields(config: dict, show_query: bool = False) -> list:
    graph_store = _configured_graph_store(config)
    if graph_store is not None:
        return graph_store.list_competitions()

    graphdb_conn = config["graphdb_conn"]
    # 关键修复：1. 不再重复声明sack_knowledge/rdfs前缀（全局PREFIXES已包含）；2. 用data:前缀对齐谓词
    sparql_query = PREFIXES + """
    SELECT ?comp_uri ?comp_name ?problem_type ?data_type
    WHERE {
        ?comp_uri a sack:Dataset ;  # 用全局定义的sack_knowledge前缀（竞赛类型）
                  rdfs:label ?comp_name ;  # 用全局定义的rdfs前缀（标签）
                  data:hasProblemType ?problem_type ;  # 用全局定义的data前缀（数据相关谓词）
                  data:hasDataType ?data_type .       # 同理，对齐前缀
    }
    """
    if show_query:
        print(f"\n【排查用SPARQL】查询所有竞赛的字段：\n{sparql_query}")

    results = query_graphdb(graphdb_conn, sparql_query, return_type='json')
    if not results:
        print("\n【排查结果】知识图谱中未查询到任何竞赛（sack:Dataset类型）的字段")
        return []

    # 整理结果（不变）
    all_competitions = []
    for res in results:
        comp_info = {
            "comp_uri": res["comp_uri"]["value"],
            "comp_name": res["comp_name"]["value"],
            "problem_type": res["problem_type"]["value"].strip(),
            "data_type": res["data_type"]["value"].strip()
        }
        all_competitions.append(comp_info)

    return all_competitions


def get_top_k_similar_competitions_core(
        config: dict,
        current_comp: Dict,
        semantic_weight: float = 0.4,
        data_weight: float = 0.6,
        show_query: bool = False
) -> pd.DataFrame:
    # 新增：1. 打印当前竞赛的初筛关键字段（用于对比）
    current_problem_type = current_comp["problem_type"].strip()
    current_data_type = current_comp["data_type"].strip()
    print("=" * 60)
    print("【初筛排查】当前竞赛的关键字段（用于匹配）：")
    print(f"  current_comp_id: {current_comp['comp_id']}")
    print(f"  current_problem_type: '{current_problem_type}'（类型：{type(current_problem_type)}）")
    print(f"  current_data_type: '{current_data_type}'（类型：{type(current_data_type)}）")
    print("=" * 60)

    # 新增：2. 查询并打印知识图谱中所有竞赛的关键字段
    all_competitions = query_all_competitions_fields(config, show_query=show_query)
    print(f"\n【初筛排查】知识图谱中共查询到 {len(all_competitions)} 个竞赛的字段：")
    if all_competitions:
        # 打印表头
        print(f"{'序号':<3} {'竞赛名称':<30} {'problem_type':<15} {'data_type':<10} {'竞赛URI（简）':<20}")
        print("-" * 80)
        # 打印每个竞赛的字段
        for i, comp in enumerate(all_competitions, 1):
            comp_uri_short = comp["comp_uri"].split("/")[-1]  # 简化URI显示
            print(
                f"{i:<3} {comp['comp_name'][:28]:<30} {comp['problem_type']:<15} {comp['data_type']:<10} {comp_uri_short:<20}")
    else:
        print("  → 未查询到任何竞赛的字段（可能图谱为空或查询谓词错误）")
    print("=" * 60)

    print(f"\n【初筛执行】用以下条件匹配：")
    print(f"  目标problem_type: '{current_problem_type}'")
    print(f"  目标data_type: '{current_data_type}'")
    # 1. 竞赛初筛（不变）
    candidate_comp_uris = filter_candidate_competitions(
        config=config,
        current_problem_type=current_comp["problem_type"],
        current_data_type=current_comp["data_type"],
        current_comp_id=current_comp["comp_id"],
        show_query=show_query
    )

    # 新增日志：打印初筛后的候选竞赛数量和ID
    print("=" * 50)
    print(f"【初筛结果】共找到 {len(candidate_comp_uris)} 个候选竞赛（problem_type/data_type匹配）")
    if candidate_comp_uris:
        for i, comp_uri in enumerate(candidate_comp_uris, 1):
            print(f"  {i}. 竞赛ID: {comp_uri}")
    else:
        print("  无候选竞赛，直接返回空结果")
        return pd.DataFrame()
    print("=" * 50)

    # 2. 计算语义相似度
    current_overview_emb = current_comp["overview_embedding"]
    semantic_scores = query_postgres_competition_semantic(
        config=config,
        emb=current_overview_emb,
        current_comp_id=current_comp["comp_id"],
        emb_col="overview_embedding",
        show_query=show_query
    )

    # 新增日志：打印每个候选竞赛的语义相似度得分
    print("\n【语义相似度得分】（基于竞赛概述匹配）")
    for comp_uri in candidate_comp_uris:
        comp_name = get_competition_name(config, comp_uri)
        score = semantic_scores.get(comp_uri, 0.0)
        print(f"  竞赛: {comp_name}（ID: {comp_uri.split('/')[-1]}） → 语义得分: {score:.3f}")
    print("=" * 50)

    # 3: 数据相似度计算
    data_scores = {}
    fasttext_model = fasttext.load_model(os.path.join(SACKKnowledgeConfig.base_dir, 'embeddings/cc.en.50.bin'))
    current_tables = current_comp["tables"]
    current_data_desc_emb = current_comp["data_description_embedding"]

    # 3.1 计算宏观数据描述相似度
    macro_data_scores = query_postgres_competition_data_desc_similarity(
        config=config,
        emb=current_data_desc_emb,
        current_comp_id=current_comp["comp_id"],
        show_query=show_query
    )

    # 新增日志：打印每个候选竞赛的宏观数据得分
    print("\n【宏观数据相似度得分】（基于数据描述匹配）")
    for comp_uri in candidate_comp_uris:
        comp_name = get_competition_name(config, comp_uri)
        score = macro_data_scores.get(comp_uri, 0.0)
        print(f"  竞赛: {comp_name}（ID: {comp_uri.split('/')[-1]}） → 宏观数据得分: {score:.3f}")
    print("=" * 50)

    # 3.2 计算微观表列匹配相似度
    micro_data_scores = {}
    print("\n【微观表列匹配得分】（基于表对+列对匹配，含细节）")

    for comp_uri in candidate_comp_uris:
        # 基于三元组查询目标竞赛的所有表
        target_tables = get_competition_tables(config=config, comp_uri=comp_uri, show_query=show_query)
        if not target_tables:
            micro_data_scores[comp_uri] = 0.0
            print(f"\n  竞赛ID: {comp_uri.split('/')[-1]} → 无表数据，微观得分: 0.0")
            continue

        # 获取竞赛名（用于日志）
        comp_name = get_competition_name(config, comp_uri)

        print(f"\n  正在处理竞赛: {comp_name}（ID: {comp_uri.split('/')[-1]}）")
        print(f"    目标竞赛包含 {len(target_tables)} 张表：{[t['table_name'] for t in target_tables]}")

        current_table_best_scores = []
        for current_table in current_tables:
            current_table_name = current_table["table_name"]
            print(f"\n    当前竞赛表: {current_table_name}（{len(current_table['columns'])} 列）")
            max_table_sim = 0.0
            best_target_table = None  # 记录匹配最佳的目标表

            for target_table in target_tables:
                target_table_name = target_table["table_name"]
                # 计算单个表对的相似度
                table_sim = calculate_table_pair_similarity(
                    config=config,
                    current_table=current_table,
                    target_table=target_table,
                    fasttext_model=fasttext_model,
                    show_query=show_query
                )
                # 新增日志：打印当前表与目标表的匹配得分
                print(f"      → 匹配目标表: {target_table_name} → 表相似度: {table_sim:.3f}")

                if table_sim > max_table_sim:
                    max_table_sim = table_sim
                    best_target_table = target_table_name

            # 记录当前表的最佳匹配得分
            current_table_best_scores.append(max_table_sim)
            print(
                f"      → 当前表 {current_table_name} 的最佳匹配表: {best_target_table} → 最佳得分: {max_table_sim:.3f}")

        # 计算该竞赛的微观总得分（所有当前表最佳得分的平均）
        if not current_table_best_scores:
            micro_score = 0.0
        else:
            micro_score = round(sum(current_table_best_scores) / len(current_table_best_scores), 3)
        micro_data_scores[comp_uri] = micro_score
        print(f"\n    竞赛 {comp_name} 微观表列总得分: {micro_score:.3f}")
    print("=" * 50)

    # 3.3 融合宏观+微观得分
    print("\n【融合数据得分】（宏观30% + 微观70%）")
    for comp_uri in candidate_comp_uris:
        comp_name = get_competition_name(config, comp_uri)

        macro_score = macro_data_scores.get(comp_uri, 0.0)
        micro_score = micro_data_scores.get(comp_uri, 0.0)
        fused_data_score = round(macro_score * 0.3 + micro_score * 0.7, 3)
        data_scores[comp_uri] = fused_data_score

        print(f"  竞赛: {comp_name}（ID: {comp_uri.split('/')[-1]}）")
        print(f"    → 宏观得分: {macro_score:.3f} × 30% = {macro_score * 0.3:.3f}")
        print(f"    → 微观得分: {micro_score:.3f} × 70% = {micro_score * 0.7:.3f}")
        print(f"    → 融合数据得分: {fused_data_score:.3f}")
    print("=" * 50)

    # 4. 融合得分并生成结果DataFrame
    result_data = []
    for comp_uri in candidate_comp_uris:
        comp_name = get_competition_name(config, comp_uri)

        # 提取得分
        sem_score = semantic_scores.get(comp_uri, 0.0)
        macro_score = macro_data_scores.get(comp_uri, 0.0)
        micro_score = micro_data_scores.get(comp_uri, 0.0)
        fused_data_score = data_scores.get(comp_uri, 0.0)
        total_score = round(sem_score * semantic_weight + fused_data_score * data_weight, 3)

        result_data.append({
            "Competition_ID": comp_uri,
            "Competition_Name": comp_name,
            "Semantic_Score": sem_score,
            "Data_Macro_Score": macro_score,
            "Data_Micro_Score": micro_score,
            "Fused_Data_Score": fused_data_score,
            "Total_Score": total_score
        })

    # 新增日志：打印最终完整得分表（排序后）
    result_df = pd.DataFrame(result_data).sort_values("Total_Score", ascending=False).reset_index(drop=True)
    print("\n【最终匹配得分表】（按总得分降序）")
    print(result_df.to_string(index=True, columns=[
        "Competition_Name", "Semantic_Score", "Data_Macro_Score",
        "Data_Micro_Score", "Fused_Data_Score", "Total_Score"
    ]))
    print("=" * 50)

    return result_df


def get_core_insights_for_pipeline_core(
        config: dict,
        pipeline_uri: str,  # 直接接收pipeline的完整URI
        show_query: bool = False
) -> pd.DataFrame:
    """
    核心函数：根据pipeline的完整URI查询其对应的所有核心见解（CoreInsight）

    参数：
        config: 配置字典（含graphdb连接等）
        pipeline_uri: pipeline的完整URI（如"http://sack.local/resource/kaggle/titanic/p1"）
        show_query: 是否打印SPARQL查询语句

    返回：
        pd.DataFrame: 核心见解结果表
    """
    # 1. 直接使用传入的pipeline_uri（无需转换）
    print("=" * 60)
    print(f"【核心见解查询】目标pipeline URI：{pipeline_uri}")
    print("=" * 60)

    # 2. 构建SPARQL查询（逻辑不变，直接使用pipeline_uri）
    query = PREFIXES + f"""
    SELECT 
        ?insight_uri
        ?description
        ?insight_type
        ?effectiveness
        ?evidence
        ?phase
        (GROUP_CONCAT(DISTINCT ?spanning_phase; SEPARATOR=", ") AS ?spanning_phases)
    WHERE {{
        <{pipeline_uri}> sack:hasCoreInsight ?insight_uri .
        ?insight_uri a sack:CoreInsight ;
                     rdfs:label ?description ;
                     sack:insightType ?insight_type ;
                     sack:effectiveness ?effectiveness ;
                     sack:evidence ?evidence ;
                     sack:belongsToPhase ?phase .
        OPTIONAL {{ ?insight_uri sack:spansPhase ?spanning_phase . }}
    }}
    GROUP BY ?insight_uri ?description ?insight_type ?effectiveness ?evidence ?phase
    """

    # 后续查询和解析逻辑不变（仅调整日志中对"pipeline_uri"的描述）
    if show_query:
        print("\n【SPARQL查询语句】")
        print(query)
        print("=" * 60)

    try:
        graphdb_conn = config["graphdb_conn"]
        results = query_graphdb(graphdb_conn, query, return_type='json')
        print(f"\n【查询结果】共找到 {len(results)} 条核心见解")
    except Exception as e:
        print(f"【查询失败】获取核心见解时出错：{str(e)}")
        return pd.DataFrame(columns=["Insight_ID", "Description", "Insight_Type", "Effectiveness", "Evidence", "Phase",
                                     "Spanning_Phases"])

    # 解析Insight_ID时，直接从insight_uri中截取（逻辑不变，因insight_uri格式依赖pipeline_uri）
    insights = []
    if results:
        for i, res in enumerate(results, 1):
            insight_uri = res["insight_uri"]["value"]
            # 从insight_uri中提取ID（依赖pipeline_uri前缀，如"http://.../insight/123" → "123"）
            insight_id = insight_uri.split(f"{pipeline_uri}/insight/")[-1]

            insights.append({
                "Insight_ID": insight_id,
                "Description": res["description"]["value"],
                "Insight_Type": res["insight_type"]["value"],
                "Effectiveness": res["effectiveness"]["value"],
                "Evidence": res["evidence"]["value"],
                "Phase": res["phase"]["value"],
                "Spanning_Phases": res.get("spanning_phases", {}).get("value", "")
            })
            description = res["description"]["value"][:100]
    else:
        print("【无结果】该pipeline未关联任何核心见解")

    return pd.DataFrame(insights)


def get_competition_field_core(
        config: dict,
        competition_uri: str,
        field: str,
        show_query: bool = False
) -> Optional[str]:
    """
    核心函数：根据竞赛名和目标字段，查询知识图谱中该竞赛的对应字段内容（修正关系标识前缀）
    """
    # 1. 修正：字段与知识图谱属性的映射（使用sackData前缀，匹配代码中的定义）
    FIELD_TO_PROPERTY = {
        "overview": "sackData:hasOverview",  # 对应代码中的sackData:hasOverview
        "data_description": "sackData:hasDataDescription",
        "problem_type": "sackData:hasProblemType",
        "data_type": "sackData:hasDataType",
        "domain": "sackData:hasDomain",
        "difficulty": "sackData:hasDifficulty"
    }

    # 2. 校验目标字段
    if field not in FIELD_TO_PROPERTY:
        raise ValueError(f"不支持的字段：{field}，支持的字段为：{list(FIELD_TO_PROPERTY.keys())}")
    target_property = FIELD_TO_PROPERTY[field]

    # 3. 构建SPARQL查询（匹配竞赛实体类型为sack:Dataset，与代码一致）
    query = f"""{PREFIXES}
    SELECT ?field_value
    WHERE {{
        <{competition_uri}> a sack:Dataset ;  
                     {target_property} ?field_value .  
    }}
    """

    if show_query:
        print("=" * 60)
        print(f"【竞赛字段查询】SPARQL语句：")
        print(query)
        print("=" * 60)

    # 4. 执行查询
    try:
        graphdb_conn = config["graphdb_conn"]
        results = query_graphdb(graphdb_conn, query, return_type='json')
        print(f"【查询结果】共找到 {len(results)} 条匹配记录")
    except Exception as e:
        print(f"【查询失败】获取竞赛字段时出错：{str(e)}")
        return None

    # 5. 解析结果
    if results:
        return results[0]["field_value"]["value"]
    else:
        print(f"【无结果】未找到竞赛 {competition_uri} 的 {field} 字段")
        return None


def get_insight_code_snippet_core(
        config: dict,
        insight_uri: str,  # 核心见解的URI（如：pipeline_uri/insight/insight_id）
        show_query: bool = False
):
    """
    核心函数：根据核心见解的URI，查询其对应的实现代码段（statement节点的hasText内容）
    """
    # 1. 构建SPARQL查询：从CoreInsight出发，通过implementedIn关联到statement，再获取hasText
    query = rf"""{PREFIXES}
    SELECT ?stmt_uri ?code_text (xsd:integer(REPLACE(STR(?stmt_uri), ".*/s(\\d+)", "$1")) AS ?order)
    WHERE {{
        <{insight_uri}> a sack:CoreInsight ;
                     sack:implementedIn ?stmt_uri .  

        ?stmt_uri pipeline:hasText ?code_text .
    }}
    ORDER BY ?order
    """

    if show_query:
        print("=" * 60)
        print(f"【见解代码段查询】SPARQL语句：")
        print(query)
        print("=" * 60)

    # 2. 执行查询（复用graphdb连接）
    try:
        graphdb_conn = config["graphdb_conn"]
        results = query_graphdb(graphdb_conn, query, return_type='json')
        print(f"【查询结果】共找到 {len(results)} 条匹配的代码段")
    except Exception as e:
        print(f"【查询失败】获取见解代码段时出错：{str(e)}")
        return None

    # 3. 解析结果
    if results:
        return results  # 返回代码文本内容
    else:
        print(f"【无结果】未找到见解 {insight_uri} 对应的实现代码段")
        return None


def get_edainsight_for_competitions_core(
        config: Dict,
        competition_uri: str,
        eda_type: str,
        show_query: bool = False
) -> Dict[str, Dict[str, Any]]:
    """
    简化后：返回结构为 {module: {field_path: value}}（不再返回DataFrame）
    直接匹配当前竞赛的结构，省去df转换步骤
    """
    if eda_type not in ["pre_eda", "deep_eda"]:
        raise ValueError(f"eda_type无效：{eda_type}")

    graph_store = _configured_graph_store(config)
    if graph_store is not None:
        return graph_store.get_eda_insight(competition_uri, eda_type)

    # 日志打印
    print("=" * 60)
    print(f"【EDAInsight查询】目标竞赛URI：{competition_uri}")
    print(f"【EDAInsight查询】目标EDA类型：{eda_type}")
    print("=" * 60)

    # 筛选当前eda_type对应的存储属性
    target_storage_attrs = [
        storage_attr for storage_attr, (e_type, _, _, _) in KG_FIELD_MAPPING.items()
        if e_type == eda_type
    ]
    if not target_storage_attrs:
        print(f"【无字段】未找到{eda_type}对应的任何字段属性")
        return {}

    # 构建SPARQL查询（无修改）
    select_clause = "?eda_uri "
    if eda_type == "pre_eda":
        e_type = "PreliminaryEDAInsight" 
    else:
        e_type = "InDepthEDAInsight"
    has_type = f"has{e_type}"
    
    where_clause_parts = [
        f"<{competition_uri}> sackData:{has_type} ?eda_uri .",
        f"?eda_uri a sack:{e_type} ;"
    ]
    for storage_attr in target_storage_attrs:
        select_clause += f"?{storage_attr} "
        sparql_predicate = f"sackData:{storage_attr}"
        where_clause_parts.append(f"{sparql_predicate} ?{storage_attr} ;")
    if where_clause_parts:
        last_part = where_clause_parts[-1].rstrip(";")  # 移除最后一个分号
        where_clause_parts[-1] = last_part + " ."  # 添加句点
    where_clause = "\n    ".join(where_clause_parts)
    
    query = PREFIXES + f"""
    SELECT {select_clause.strip()}
    WHERE {{
        {where_clause}
    }}
    """

    if show_query:
        print("\n【SPARQL查询语句】")
        print(query)
        print("=" * 60)

    # 执行查询
    try:
        graphdb_conn = config["graphdb_conn"]
        results = query_graphdb(graphdb_conn, query, return_type='json')
        print(f"\n【查询结果】共找到 {len(results)} 条EDAInsight记录（节点）")
    except Exception as e:
        print(f"【查询失败】获取EDAInsight时出错：{str(e)}")
        return {}

    # 解析结果：直接组织为module→field_path→value（核心简化点）
    eda_data = {}  # module → field_path → value
    if results:
        res = results[0]
        eda_uri = res["eda_uri"]["value"]
        print(f"【EDA节点URI】{eda_uri}")

        for storage_attr in target_storage_attrs:
            # 获取字段元信息
            e_type, module, field_path, field_type = KG_FIELD_MAPPING[storage_attr]
            # 获取值并转换类型
            value_obj = res.get(storage_attr, {})
            raw_value = value_obj.get("value", "unknown") if value_obj else "unknown"

            # 类型转换（匹配当前竞赛的数值类型）
            try:
                if field_type == "float":
                    value = float(raw_value) if raw_value != "unknown" else "unknown"
                elif field_type == "boolean":
                    value = raw_value.lower() == "true" if raw_value != "unknown" else "unknown"
                elif field_type == "json":
                    value = json.loads(raw_value) if raw_value != "unknown" else "unknown"
                else:
                    value = raw_value
            except (ValueError, json.JSONDecodeError):
                value = "unknown"

            # 填充module→field_path→value
            if module not in eda_data:
                eda_data[module] = {}
            eda_data[module][field_path] = value

    else:
        print(f"【无结果】该竞赛未关联任何{eda_type}类型的EDAInsight")

    return eda_data  # 直接返回核心结构，不再返回DataFrame


def get_top_k_edainsight_similar_competitions_core(
        config: Dict,
        current_comp_info: Dict,
        current_comp_edainsight: Dict[str, Dict[str, Dict[str, Any]]],
        show_query: bool = False
) -> List[Dict[str, Any]]:
    """
    修改点：
    1. 返回结果从List[Tuple[str, float]]改为List[Dict]，包含竞赛URI、总相似度、各模块相似度
    2. 新增收集各模块相似度明细
    """
    current_comp_id = current_comp_info["comp_id"]
    current_competition_uri = f"http://sack.local/resource/{current_comp_id}"

    similarity_results = []
    candidate_comp_uris = filter_candidate_competitions(
        config=config,
        current_problem_type=current_comp_info["problem_type"],
        current_data_type=current_comp_info["data_type"],
        current_comp_id=current_comp_id,
        show_query=show_query
    )

    for comp_uri in candidate_comp_uris:
        if comp_uri == current_competition_uri:
            continue

        # 检索目标竞赛的EDA数据（原逻辑不变）
        target_edainsight = {}
        for eda_type in ["pre_eda", "deep_eda"]:
            target_edainsight[eda_type] = get_edainsight_for_competitions_core(
                config=config,
                competition_uri=comp_uri,
                eda_type=eda_type,
                show_query=show_query
            )

        # 计算相似度：获取总相似度+模块明细（修改点）
        similarity_detail = calculate_stage_similarity(current_comp_edainsight, target_edainsight)

        # 构造结果字典：包含竞赛URI、总相似度、各模块相似度
        result_dict = {
            "comp_uri": comp_uri
        }

        # 遍历相似度明细，扁平化为字段名（避免嵌套，方便DataFrame处理）
        for eda_type, module_dict in similarity_detail.items():
            for module, sim in module_dict.items():
                # 字段名格式：eda类型_模块名（小写，空格替换为下划线）
                field_name = f"{eda_type}_{module}".replace(" ", "_").lower()
                result_dict[field_name] = sim

        similarity_results.append(result_dict)

    # 按总相似度降序排序，取Top-K
    similarity_results.sort(key=lambda x: x["pre_eda_data_quality"], reverse=True)
    return similarity_results
