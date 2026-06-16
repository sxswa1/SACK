import chromadb
from chromadb.api.client import Client
import re
from tqdm import tqdm
import json

# from SOP import SOP
from sack.LLMComponent.llm import OpenaiEmbeddings

import logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.WARNING)

def split_sklearn(text: str, max_chunk_length: int = 8191, overlap_ratio: float = 0.1):  # 涓€涓畬鏁磗klearn宸ュ叿鎷嗗垎鎴愬涓猚hunk
    if not (0 <= overlap_ratio < 1):
        raise ValueError("Overlap ratio must be between 0 and 1 (exclusive).")
    
    # Calculate the length of overlap in characters
    overlap_length = int(max_chunk_length * overlap_ratio)
    chunks = []
    start = 0
    
    while start < len(text):
        end = min(start + max_chunk_length, len(text))
        chunk = text[start:end]
        chunks.append(chunk)
        start += max_chunk_length - overlap_length # 姣忎釜chunk鍙敤鐨勫彧鏈塵ax_chunk_length - overlap_length闀垮害
        
    return chunks


def split_tools(text: str): # 工具的chunk划分直接用---
    # Split the text into chunks
    chunks = re.split(r'---', text)
    return chunks

class KnowledgeBase:
    def __init__(self, client: Client, collection_name: str, embedding_model: OpenaiEmbeddings):
        self.chroma_client = client
        self.collection_name = collection_name
        # choose cosine similarity for the search
        self.collection = self.chroma_client.get_or_create_collection(self.collection_name, metadata={"hnsw:space": "cosine"}) 

        # Load the embedding model 
        self.embedding_model = embedding_model
        self.id = 0 # the id of the data in the collection
        
    def insert_vectors(self, chunks: list, doc_name: str): # collection娣诲姞鍐呭
        results = chunks
        # insert the vectors into the collection
        for result in tqdm(results):
            text_embedding = self.embedding_model.encode(input=result)[0].embedding

            metadata = {
                'doc name': doc_name,
            }

            # insert the vectors into the collection
            self.collection.add(
                documents=result,
                ids=f'{self.id}',
                embeddings=text_embedding,
                metadatas=metadata
            )
            self.id += 1
        print('---------------------------------')
        print(f'Finished inserting vectors for <{self.collection_name}>!')
        print('---------------------------------')

    # use the query to search the most similar context
    def search_context(self, query: str, n_results=5) -> dict:  # 相似性检索
        query_embeddings = self.embedding_model.encode(query)[0].embedding
        results =  self.collection.query(query_embeddings=query_embeddings, n_results=n_results, include=['documents', 'distances', 'metadatas'])
        return results
    
    def search_context_with_metadatas(self, query: str, label: str, n_results=5) -> dict: # 在collection中检索某个工具
        query_embeddings = self.embedding_model.encode(query)[0].embedding
        results = self.collection.query(
            query_embeddings=query_embeddings, n_results=n_results, 
            include=['documents', 'distances', 'metadatas'], 
            where={'doc name': label} # 在某个阶段的工具里寻找 label就是阶段对应的文档名 如 data_cleaning_tools.md
        )
        return results
    
    def check_collection_none(self): # 杩斿洖collection鍐卍oc涓暟
        document_count = self.collection.count()
        if document_count == 0:
            print("The collection is empty.")
        else:
            print(f"The collection has {document_count} documents.")

        return document_count
