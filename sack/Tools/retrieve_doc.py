import os
import chromadb
from tqdm import tqdm
from html2text import html2text

from sack.api_handler import load_api_config
from sack.LLMComponent.llm import OpenaiEmbeddings, LLM
from sack.LLMComponent.knowledge_base import KnowledgeBase, split_sklearn, split_tools
from sack.paths import SACK_PACKAGE_DIR
# from state import State


class RetrieveTool:
    def __init__(self, model: str, embeddings: OpenaiEmbeddings, doc_path: str = 'Tools/ml_tools_doc', collection_name: str = 'tools'):
        self.llm = model
        self.embeddings = embeddings
        self.doc_path = str(SACK_PACKAGE_DIR / doc_path)
        chroma_db_path = os.environ.get("SACK_CHROMA_DB_PATH", str(SACK_PACKAGE_DIR / 'LLMComponent' / 'db'))
        self.client = chromadb.PersistentClient(path=chroma_db_path)
        self.collection_name = collection_name

        self.db = KnowledgeBase(self.client, self.collection_name, self.embeddings)
 
    def create_db_sklearn(self, doc_type: str = '.rst'): # or .html  创建sklearn工具专门的知识库
        rst_path = []
        if os.path.exists(self.doc_path) and os.path.isdir(self.doc_path):
            for file in os.listdir(self.doc_path):  # 这里文件夹没有这些内容 可能要单独提取
                # Ensure it checks only files in 'pandas/reference' and not sub-folders
                file_path = os.path.join(self.doc_path, file)
                # read .rst files
                if os.path.isfile(file_path) and file.endswith(doc_type):  # 没有 rst 文件，目前只有 md 文件。
                    rst_path.append(file_path)
        
        # Read the HTML files   
        for path in tqdm(rst_path): # rst里可能是工具的html地址？
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
                content = html2text(content)
                chunks = split_sklearn(content) # sklearn工具入知识库
                self.db.insert_vectors(chunks, path)

    def query_sklearn(self, query: str): # 工具检索
        results = self.db.search_context(query) #检索最相关的5个结果
        path = results['metadatas'][0][0]['doc name']
        details = []
        for i in results['metadatas'][0]: # 把最相关的5个工具的html文本加载进去（也就是tools）
            path = i['doc name']
            # open the html file
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
                content = html2text(content)
                details.append(content)

        prompt = ''' Based on the instruction "{details}", extract the top-3 most relevant key information from the following text. Just output in the following json format:
{{
    "name of the function 1": {{str="exaplantion of function 1", str="code example of function 1"}},
    "name of the function 2": {{str="exaplantion of function 2", str="code example of function 2"}},
    "name of the function 3": {{str="exaplantion of function n", str="code example of function 3"}}
}}

text: {content}
'''
        prompt = prompt.format(details=details, content=content)  # 检查匹配结果中的 content 字段。
        conclusion, _ = self.llm.generate(prompt, history=None) # 让大模型从最相关的5个里再挑出来三个工具
        
        return conclusion
    
    def create_db_tools(self, doc_type: str = '.md'): # 创建完整工具库（所有DSpipeline阶段，因为其他阶段不用ML工具）
        md_path = []
        if os.path.exists(self.doc_path) and os.path.isdir(self.doc_path):
            for file in os.listdir(self.doc_path): # data cleaning   feature engineering  model build 各阶段的ml工具文档（.md）
                # Ensure it checks only files in 'pandas/reference' and not sub-folders
                file_path = os.path.join(self.doc_path, file)
                # read .rst files
                if os.path.isfile(file_path) and file.endswith(doc_type):
                    md_path.append(file_path)

        # Read the HTML files
        num_data = self.db.check_collection_none() # 返回collection
        if num_data == 0: # collection is empty, need to find Tools from html
            for path in tqdm(md_path):
                with open(path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    chunks = split_tools(content)  # 工具切分chunk并入库
                    self.db.insert_vectors(chunks, os.path.basename(path)) # 使用路径对象获取文件名，兼容 Windows 路径分隔符。

    def query_tools(self, query: str, state_name: str='data_cleaning'): # 检索 query 指定的当前阶段工具。
        label = state_name + '_tools.md' # 各阶段可用的工具不同。
        # print(self.db.collection.get())
        results = self.db.search_context_with_metadatas(query, label)
        # print(results)
        return results['documents'][0][0]
