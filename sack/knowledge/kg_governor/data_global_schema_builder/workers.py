import os
import random
import string

import numpy as np

from sack.knowledge.kg_governor.data_global_schema_builder.utils.utils import generate_label, RDFResource, Triplet


def column_metadata_worker(column_profiles,  ontology, triples_output_tmp_dir):
    # TODO: [Refactor] have the names of predicates read from global project ontology object
    triples = []
    
    for column_profile in column_profiles:
        # col_name = column_profile.get_column_name()
        # if col_name is None or not col_name.strip():
        #     # 打印问题数据的table_id和column_id，方便排查
        #     dataset_id = column_profile.get_dataset_id()
        #     table_id = column_profile.get_table_id()
        #     column_id = column_profile.get_column_id()
        #     print(f"Warning: Empty column name found! path = {path}, dataset_id= {dataset_id}, table_id={table_id}, column_id={column_id}")
        #     raise 

        column_node = RDFResource(column_profile.get_column_id(), ontology['sackResource'])
        table_node = RDFResource(column_profile.get_table_id(), ontology['sackResource'])
        col_label = generate_label(column_profile.get_column_name(), 'en')

        # membership
        triples.append(Triplet(column_node, RDFResource('isPartOf', ontology['sack_knowledge']), table_node))
        triples.append(Triplet(column_node, RDFResource('type', ontology['rdf']),
                               RDFResource('Column', ontology['sack_knowledge'])))
        # metadata
        triples.append(Triplet(column_node, RDFResource('hasDataType', ontology['sackData']),
                               RDFResource(column_profile.get_data_type())))
        triples.append(Triplet(column_node, RDFResource('name', ontology['schema']),
                               RDFResource(column_profile.get_column_name())))
        triples.append(Triplet(column_node, RDFResource('hasTotalValueCount', ontology['sackData']),
                               RDFResource(column_profile.get_total_values_count())))
        triples.append(Triplet(column_node, RDFResource('hasDistinctValueCount', ontology['sackData']),
                               RDFResource(column_profile.get_distinct_values_count())))
        triples.append(Triplet(column_node, RDFResource('hasMissingValueCount', ontology['sackData']),
                               RDFResource(column_profile.get_missing_values_count())))
        triples.append(Triplet(column_node, RDFResource('label', ontology['rdfs']), RDFResource(col_label)))

        if column_profile.is_numeric():
            triples.append(Triplet(column_node, RDFResource('hasMedianValue', ontology['sackData']),
                                   RDFResource(column_profile.get_median())))
            triples.append(Triplet(column_node, RDFResource('hasMaxValue', ontology['sackData']),
                                   RDFResource(column_profile.get_max_value())))
            triples.append(Triplet(column_node, RDFResource('hasMinValue', ontology['sackData']),
                                   RDFResource(column_profile.get_min_value())))
        
        if column_profile.is_boolean():
            triples.append(Triplet(column_node, RDFResource('hasTrueRatio', ontology['sackData']),
                                   RDFResource(column_profile.get_true_ratio())))

    filename = ''.join(random.choices(string.ascii_letters + string.digits, k=15)) + '.nt'
    with open(os.path.join(triples_output_tmp_dir, filename), 'w', encoding='utf-8') as f:
        for triple in triples:
            f.write(f"{triple}\n")
    
    return []
    
        
def column_pair_similarity_worker(column_idx, column_profiles, ontology, triples_output_tmp_dir,
                                  label_sim_threshold, embedding_sim_threshold, boolean_sim_threshold,
                                  word_embedding):

    # load the column profiles
    column1_profile = column_profiles[column_idx]
    similarity_triples = []
    for j in range(column_idx+1, len(column_profiles)):
        column2_profile = column_profiles[j]
        
        # don't compare if the data type is different or the columns are in the same table.
        if column1_profile.get_data_type() != column2_profile.get_data_type():
            continue
        if column1_profile.get_table_id() == column2_profile.get_table_id():
            continue

        label_sim_triples = _compute_label_similarity(column1_profile, column2_profile, ontology,
                                                      label_sim_threshold, word_embedding)
        content_sim_triples = _compute_content_similarity(column1_profile, column2_profile, ontology,
                                                          embedding_sim_threshold, boolean_sim_threshold)

        similarity_triples.extend(label_sim_triples + content_sim_triples)
        
    filename = ''.join(random.choices(string.ascii_letters + string.digits, k=15)) + '.nt'
    with open(os.path.join(triples_output_tmp_dir, filename), 'w', encoding='utf-8') as f:
        for triple in similarity_triples:
            f.write(f"{triple}\n")
            
    return []
        

def _compute_label_similarity(column1_profile, column2_profile, ontology,
                              label_similarity_threshold: float, word_embedding_model) -> list:
    # TODO: [Refactor] have the names of predicates read from global project ontology object

    column1_label = generate_label(column1_profile.get_column_name(), 'en').get_text()
    column2_label = generate_label(column2_profile.get_column_name(), 'en').get_text()
    
    score = word_embedding_model.get_distance_between_column_labels(column1_label, column2_label)
    label_similarity_triples = []
    if score >= label_similarity_threshold:
        label_similarity_triples.extend(_create_column_similarity_triples(column1_profile, column2_profile, 
                                                                          'hasLabelSimilarity', score, ontology))
    return label_similarity_triples


def _compute_content_similarity(col1_profile, col2_profile, ontology, embedding_sim_threshold, boolean_sim_threshold):
    content_sim_triples = []
    if col1_profile.is_boolean():
        boolean_sim = 1 - np.abs(col1_profile.get_true_ratio() - col2_profile.get_true_ratio()) 
        if boolean_sim >= boolean_sim_threshold:
            content_sim_triples.extend(_create_column_similarity_triples(col1_profile, col2_profile,
                                                                         'hasContentSimilarity', boolean_sim,
                                                                         ontology))
    else:
        # Calculate similarity using CoLR embedding and scaling factor
        embedding_dist = np.linalg.norm(np.array(col1_profile.get_embedding()) - np.array(col2_profile.get_embedding()))
        colr_distance = embedding_dist + col1_profile.get_embedding_scaling_factor() \
                        + col2_profile.get_embedding_scaling_factor()
        colr_similarity = 1 - np.tanh(colr_distance)
        
        if colr_similarity >= embedding_sim_threshold:
            content_sim_triples.extend(_create_column_similarity_triples(col1_profile, col2_profile,
                                                                         'hasContentSimilarity', colr_similarity,
                                                                         ontology))
    return content_sim_triples


# TODO: [Refactor] this method needs to be moved somewhere else.
# TODO: [Refactor] this method shouldn't take ontology from the worker methods. It should be passed from global config
def _create_column_similarity_triples(column1_profile, column2_profile,
                                      similarity_predicate, similarity_score, ontology):
    nested_subject = RDFResource(column1_profile.get_column_id(), ontology['sackResource'])
    nested_predicate = RDFResource(similarity_predicate, ontology['sackData'])
    nested_object = RDFResource(column2_profile.get_column_id(), ontology['sackResource'])
    # RDF-star triple of the content similarity between the two columns with the score.
    triple = Triplet(Triplet(nested_subject, nested_predicate, nested_object),
                     RDFResource('withCertainty', ontology['sackData']), RDFResource(similarity_score))
    return [triple, triple.get_reversed_triple()]


