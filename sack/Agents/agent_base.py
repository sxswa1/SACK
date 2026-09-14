# agents/agent_base.py

from typing import Dict, Any
import json
import re
import logging
import os
import pdb
import glob
import pandas as pd
from docx import Document
import chardet


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

from sack.utils import read_file
from sack.state import State
from sack.paths import SACK_CONFIG_PATH
from sack.Prompts.prompt_base import *
from typing import Tuple, List


class Agent:
    def __init__(self, role: str, description: str, model: str, type: str):
        from sack.LLMComponent.llm import LLM

        self.role = role
        self.description = description
        self.llm = LLM(model, type)
        self.model = model
        logger.info(f'Agent {self.role} is created with model {model}.')
        self._sack_case_retriever = None

    @property
    def sack_case_retriever(self):
        if self._sack_case_retriever is None:
            from sack.Agents.agent_retriever import SACKCaseRetriever

            self._sack_case_retriever = SACKCaseRetriever(
                kg_endpoint='http://localhost:7200',
                kg_db='kaggle'
            )
        return self._sack_case_retriever

    def has_sack_case_retriever(self) -> bool:
        try:
            _ = self.sack_case_retriever
            return True
        except Exception as exc:
            logger.warning("SACKCaseRetriever unavailable; continuing without case retrieval: %s", exc)
            return False

    def get_sack_case_retriever(self):
        if not self.has_sack_case_retriever():
            return None
        return self._sack_case_retriever

    def _gather_experience_with_suggestion(self, state: State) -> str:  # 获取过往轮次的经验，指导下一轮迭代
        experience_with_suggestion = ""
        for i, each_state_memory in enumerate(state.memory[:-1]):
            act_agent_memory = each_state_memory.get(self.role,
                                                     {})  # get the memory of the current agent in the past state
            result = act_agent_memory.get("result", "")
            reviewer_memory = each_state_memory.get("reviewer", {})  # get the memory of the reviewer in the past state
            suggestion = reviewer_memory.get("suggestion", {}).get(f"agent {self.role}", "")
            score = reviewer_memory.get("score", {}).get(f"agent {self.role}", 3)
            experience_with_suggestion += PROMPT_EACH_EXPERIENCE_WITH_SUGGESTION.format(index=i, experience=result,
                                                                                        suggestion=suggestion,
                                                                                        score=score)  # 加载经验提示词
            if self.role == 'developer':  # 针对develop和reviewer之间的经验迭代  还要加载错误日志和reviewer的建议
                path_to_error = f'{state.restore_dir}/{state.dir_name}_error.txt'
                path_to_not_pass_info = f'{state.restore_dir}/{state.dir_name}_not_pass_information.txt'
                if os.path.exists(path_to_error):
                    with open(path_to_error, 'r', encoding='utf-8') as f:
                        error_message = f.read()
                    experience_with_suggestion += f"\n<ERROR MESSAGE>\n{error_message}\n</ERROR MESSAGE>"
                elif os.path.exists(path_to_not_pass_info):
                    with open(path_to_not_pass_info, 'r', encoding='utf-8') as f:
                        not_pass_info = f.read()
                    experience_with_suggestion += f"\n<NOT PASS INFORMATION>\n{not_pass_info}\n</NOT PASS INFORMATION"
        return experience_with_suggestion

    def _read_data(self, state: State, num_lines: int = 11) -> str:  # 对数据集的信息读取,不同阶段要看阶段性产出的数据

        if state.phase in ["Data Preparation"]:  # 数据准备阶段。
            rawdata_path = f'{state.competition_dir}/rawdata'
            file_path_list = []
            try:
                for item in os.listdir(rawdata_path):
                    item_path = os.path.join(rawdata_path, item)
                    if os.path.isfile(item_path):
                        file_path_list.append(item_path)
            except Exception as e:
                print(f"Error reading directory {rawdata_path}: {e}")
            result = "#############\n# AVAILABLE FILES #\n{}".format("\n".join(file_path_list))

            def read_file_lines(file_path, num_lines=10):
                """读取文件前几行，支持多种文件类型"""
                file_ext = os.path.splitext(file_path)[1].lower()
                try:
                    if file_ext == '.txt':
                        with open(file_path, 'rb') as f:
                            a = chardet.detect(f.read())
                        # 获取行数和列数
                        with open(file_path, 'r',encoding=a['encoding'],errors='ignore') as f:
                            lines = f.readlines()
                            return lines[:100]

                    elif file_ext == '.xlsx' or file_ext == '.xls':
                        # 使用 pandas 读取 Excel 文件的前几行。
                        df = pd.read_excel(file_path, header=None)
                        df = df.dropna(how='all')
                        df = df.head(num_lines)
                        tsv_data = df.to_csv(sep='\t', na_rep='nan', index=False,header=False)

                        return tsv_data.split('\n')


                    elif file_ext == '.csv':
                        # 先尝试UTF-8编码
                        try:
                            df_utf8 = pd.read_csv(file_path, nrows=num_lines, encoding='utf-8')
                            df_utf8 =  df_utf8.dropna(how='all')
                            # 检查是否含有常见乱码字符。
                            if not df_utf8.applymap(lambda x: any(c in str(x) for c in ('�', '锟', '茂', '驴', '陆'))).any().any():
                                tsv_data = df_utf8.to_csv(sep='\t', na_rep='nan', index=False)
                            return tsv_data.split('\n')
                        except (UnicodeDecodeError, pd.errors.ParserError):
                            pass  # 如果读取失败，继续尝试 GBK 编码。
                        # 再尝试GBK编码
                        try:
                            df_gbk = pd.read_csv(file_path, nrows=num_lines, encoding='gbk')
                            df_gbk = df_gbk.dropna(how='all')
                            tsv_data = df_gbk.to_csv(sep='\t', na_rep='nan', index=False)
                            return tsv_data.split('\n')
                        except (UnicodeDecodeError, pd.errors.ParserError):
                            # 两种编码均失败时，使用错误替换策略。
                            try:
                                df = pd.read_csv(file_path, nrows=num_lines, encoding='utf-8', errors='replace')
                                df = df.dropna(how='all')
                                tsv_data = df.to_csv(sep='\t', na_rep='nan', index=False)
                                return tsv_data.split('\n')
                            except Exception as e:
                                return [f"错误：无法读取文件 - {str(e)}"]


                    elif file_ext in ['.parquet', '.parq']:
                        # 3) 最后兜底：utf-8 + replace，至少保证不报错
                        df = pd.read_parquet(file_path)
                        # 3) 最后兜底：utf-8 + replace，至少保证不报错
                        content = df.head(num_lines).to_csv(sep='\t', na_rep='nan', index=False)
                        # 获取总行数、列数和列名
                        rows, columns = df.shape
                        column_names = df.columns.tolist()
                        return content, rows, columns, column_names
                        
                    elif file_ext == '.docx':
                        # 读取 docx 文件
                        doc = Document(file_path)
                        return [para.text.strip() for para in doc.paragraphs[:100] if para.text.strip()]

                    else:
                        return [f"不支持的文件类型: {file_ext}"]

                except Exception as e:
                    return [f"读取文件时出错 ({file_path}): {str(e)}"]

            all_file_preview="\n#############\n# FILE PREVIEW #"
            for file_path in file_path_list:
                file_name = os.path.basename(file_path)
                file_pre= read_file_lines(file_path, num_lines=num_lines)
                file_pre = "".join(file_pre)
                all_file_preview += f"\n{file_name}:\n{file_pre}"
            result += all_file_preview

        else:
            def read_sample(file_path: str, num_lines) -> str:
                """
                read the first num_lines lines of a file and return as a string
                """
                sample_lines = []
                with open(file_path, 'r', encoding='utf-8') as f:
                    for i, line in enumerate(f):
                        if i >= num_lines:
                            break
                        sample_lines.append(line)
                return "".join(sample_lines)

            submission_columns = pd.read_csv(f'{state.competition_dir}/sample_submission.csv').columns.tolist()
            target_columns = submission_columns[1:]  # 限定目标变量在指定列后的内容中。
            result = f"\n#############\n# TARGET VARIABLE #\n{target_columns}"
            if state.phase in ["Understand Background", "Preliminary Exploratory Data Analysis", "Data Cleaning","PEDA Insight Extraction"]:
                train_data_sample = read_sample(f'{state.competition_dir}/train.csv',
                                                num_lines)  # 这里已经限定数据一定是一个train.csv 一个test.csv 会把前11行数据读入大模型，让他分析数据集信息
                test_data_sample = read_sample(f'{state.competition_dir}/test.csv', num_lines)
                result += f"\n#############\n# TRAIN DATA WITH FEATURES #\n{train_data_sample}\n#############\n# TEST DATA WITH FEATURES #\n{test_data_sample}"
            elif state.phase in ["In-depth Exploratory Data Analysis", "Feature Engineering","IEDA Insight Extraction"]:
                cleaned_train_data_sample = read_sample(f'{state.competition_dir}/cleaned_train.csv', num_lines)
                cleaned_test_data_sample = read_sample(f'{state.competition_dir}/cleaned_test.csv', num_lines)
                result += f"\n#############\n# CLEANED TRAIN DATA WITH FEATURES #\n{cleaned_train_data_sample}\n#############\n# CLEANED TEST DATA WITH FEATURES #\n{cleaned_test_data_sample}"
            elif state.phase in ["Model Building, Validation, and Prediction"]:
                processed_train_data_sample = read_sample(f'{state.competition_dir}/processed_train.csv', num_lines)
                processed_test_data_sample = read_sample(f'{state.competition_dir}/processed_test.csv', num_lines)
                submission_sample = read_sample(f'{state.competition_dir}/sample_submission.csv', num_lines)
                result += f"\n#############\n# PROCESSED TRAIN DATA WITH FEATURES #\n{processed_train_data_sample}\n#############\n# PROCESSED TEST DATA WITH FEATURES #\n{processed_test_data_sample}\n#############\n# SUBMISSION FORMAT #\n{submission_sample}"
                with open(f'{state.competition_dir}/competition_info.txt', 'r', encoding='utf-8') as f:
                    competition_info = f.read()
                prompt_extract_metric = f"# TASK #\nPlease extract the evaluation metric from the competition information: {competition_info}\n#############\n# RESPONSE: MARKDOWN FORMAT #\n```markdown\n# Evaluation Metric\n[evaluation metric for the competition]\n```"
                raw_reply, _ = self.llm.generate(prompt_extract_metric, history=[], max_completion_tokens=4096)
                metric = self._parse_markdown(raw_reply)
                result += f"\n#############\n# EVALUATION METRIC #\n{metric}"
        return result




    def _data_preview(self, state: State, num_lines: int) -> str:  # 读取数据集内容，对让大模型理解数据形态
        if state.phase != "Data Preparation":
            data_used_in_preview = self._read_data(state, num_lines=num_lines)
            input = PROMPT_DATA_PREVIEW.format(data=data_used_in_preview)
            raw_reply, _ = self.llm.generate(input, [], max_completion_tokens=4096)
            data_preview = self._parse_markdown(raw_reply)
        else:
            data_preview = self._read_data(state, num_lines=num_lines) # 数据准备阶段直接返回可用数据文件和样例，无需让模型分析数据。

        with open(f'{state.restore_dir}/data_preview.txt', 'w',encoding='utf-8') as f:
            f.write(data_preview)
        return data_preview

    def _parse_json(self, raw_reply: str) -> Dict[str, Any]:  # 把大模型返回的json text 提取成json
        def try_json_loads(data: str) -> Dict[str, Any]:
            try:
                return json.loads(data)
            except json.JSONDecodeError as e:
                logging.error(f"JSON decoding error: {e}")
                return None

        raw_reply = raw_reply.strip()
        logger.info(f"Attempting to extract JSON from raw reply.")
        json_match = re.search(r'```json(.*)```', raw_reply, re.DOTALL)  # greedy mode capture

        if json_match:
            reply_str = json_match.group(1).strip()
            reply = try_json_loads(reply_str)
            if reply is not None:
                return reply

        # 如果提取失败，针对不同场景让模型重组 JSON 格式。
        logger.info(f"Failed to parse JSON from raw reply, attempting reorganization.")
        if self.role == 'developer':
            # 确保内容是字符串
            json_reply, _ = self.llm.generate(PROMPT_REORGANIZE_EXTRACT_TOOLS.format(information=raw_reply), history=[],
                                              max_completion_tokens=4096)
        else:
            # 其他情况的json都只需要要求充足成json格式即可，没有具体字段格式定义
            json_reply, _ = self.llm.generate(PROMPT_REORGANIZE_JSON.format(information=raw_reply), history=[],
                                              max_completion_tokens=4096)

        json_match = re.search(r'```json(.*?)```', json_reply, re.DOTALL)  # 重新提取json
        if json_match:
            reply_str = json_match.group(1).strip()
            reply = try_json_loads(reply_str)

            if reply is not None:
                return reply

        logging.error("Final attempt to parse JSON failed.")
        reply = {}

        return reply

    def _parse_markdown(self, raw_reply: str) -> str:
        markdown_match = re.search(r'```markdown(.*)```', raw_reply, re.DOTALL)
        if markdown_match:
            reply_str = markdown_match.group(1).strip()
            return reply_str
        else:
            print(self.role)
            logging.error("Failed to parse markdown from raw reply.")  # 无法解析markdown格式
            # pdb.set_trace()
            return raw_reply

    def _json_to_markdown(self, json_data):  # json格式转markdown
        md_output = f"## {json_data['name']}\n\n"
        md_output += f"**Name:** {json_data['name']}  \n"
        md_output += f"**Description:** {json_data['description']}  \n"
        md_output += f"**Applicable Situations:** {json_data['applicable_situations']}\n\n"

        md_output += "**Parameters:**\n"
        for param, details in json_data['parameters'].items():
            md_output += f"- `{param}`:\n"
            md_output += f"  - **Type:** `{details['type'] if isinstance(details['type'], str) else ' | '.join(f'`{t}`' for t in details['type'])}`\n"
            md_output += f"  - **Description:** {details['description']}\n"
            if 'enum' in details:
                md_output += f"  - **Enum:** {' | '.join(f'`{e}`' for e in details['enum'])}\n"
            if 'default' in details:
                md_output += f"  - **Default:** `{details['default']}`\n"

        md_output += f"\n**Required:** {', '.join(f'`{r}`' for r in json_data['required'])}  \n"
        md_output += f"**Result:** {json_data['result']}  \n"

        md_output += "**Notes:**\n"
        for note in json_data['notes']:
            md_output += f"- {note}\n"

        if 'example' in json_data:
            md_output += "**Example:**\n"
            md_output += f"  - **Input:**\n"
            for key, value in json_data['example']['input'].items():
                md_output += f"    - `{key}`: {value}\n"
            md_output += f"  - **Output:**\n"
            for key, value in json_data['example']['output'].items():
                md_output += f"    - `{key}`: {value}\n"

        md_output += "\n---\n"
        return md_output

    def _get_tools(self, state: State) -> Tuple[str, List[str]]:  #获取当前阶段可用工具（ml工具）
        from sack.api_handler import load_api_config
        from sack.LLMComponent.llm import OpenaiEmbeddings
        from sack.Tools.retrieve_doc import RetrieveTool

        embeddings = OpenaiEmbeddings(api_key=load_api_config()[0], base_url=load_api_config()[1])
        if state.phase in ['Data Cleaning','Feature Engineering','Model Building, Validation, and Prediction']:
            memory = RetrieveTool(self.llm, embeddings, doc_path='Tools/ml_tools_doc',
                                  collection_name='ml_tools')  # 工具库（所有阶段的工具在一块）  第一次调用就把所有ml工具都创建
            # update the memory
            memory.create_db_tools()  # 添加所有可用工具(工具描述入库，md)
        elif state.phase in ['PEDA Insight Extraction','IEDA Insight Extraction']:
            memory = RetrieveTool(self.llm, embeddings, doc_path='Tools/eda_tools_doc',
                                  collection_name='eda_tools')  # 工具库（所有阶段的工具在一块）  第一次调用就把所有eda工具都创建
            memory.create_db_tools()

        state_name = state.dir_name  # 当前阶段对应的文件夹名。
        with open(SACK_CONFIG_PATH, 'r', encoding='utf-8') as file:
            config = json.load(file)
        phase_to_dir = [key for key, value in config['phase_to_directory'].items() if value == state_name][0]  # 阶段名（这不是脱裤子放屁吗直接state.phase不就行吗）
        # print(phase_to_dir)
        if state.use_mode == "DSPipeline":
            all_tool_names = config['phase_to_ml_tools'][phase_to_dir]  # 读取阶段所有可用工具名（对应的工具已经入阶段的工具库了）
        else:
            all_tool_names = config['_phase_to_ml_tools'][phase_to_dir]


        # developer只在DSPipeline使用ml工具（其他阶段本来也不使用ml工具）
        if self.role == 'developer' and state.phase in ['PEDA Insight Extraction','Data Cleaning','IEDA Insight Extraction',
                                                        'Feature Engineering','Model Building, Validation, and Prediction'] and len(all_tool_names) > 0:
            logger.info(f"Extracting Tools' description for developer in phase: {state.phase}")
            with open(f'{state.restore_dir}/markdown_plan.txt', 'r', encoding='utf-8') as file:  # 当前阶段目录下的 markdown_plan.txt，即该阶段的计划。
                markdown_plan = file.read()  # 阶段的plan，里边有plan涉及的所有工具
            input = PROMPT_EXTRACT_TOOLS.format(document=markdown_plan,
                                                all_tool_names=all_tool_names)  # 要求从库中检索当前阶段的plan中提到的所有可用工具
            raw_reply, _ = self.llm.generate(input, history=[], max_completion_tokens=4096)
            with open(f'{state.restore_dir}/extract_tools_reply.txt', 'w', encoding='utf-8') as file:
                file.write(raw_reply)  # 将计划涉及的工具保存到当前阶段记忆中。
            tool_names = self._parse_json(raw_reply)['tool_names']
        else:
            tool_names = all_tool_names  # 当前阶段所有工具

        # print("当前阶段所有工具的名字：",tool_names)  # 数据清理阶段有具体工具

        tools = []
        for tool_name in tool_names:  # 检索需要的工具  planner要所有的  developer要planner提到的
            conclusion = memory.query_tools(f'Use the {tool_name} tool.', state_name)
            tools.append(conclusion)

        if self.role == 'developer' and state.phase in ['PEDA Insight Extraction',
                                                        'IEDA Insight Extraction',
                                                        'Data Cleaning',
                                                        'Feature Engineering',
                                                        'Model Building, Validation, and Prediction']:
            with open(f'{state.restore_dir}/tools_used_in_{state.dir_name}.md', 'w', encoding='utf-8') as file:  # 在阶段目录下记录计划使用的工具。
                file.write(''.join(tools))

        tools = ''.join(tools) if len(tool_names) > 0 else "There is no pre-defined Tools used in this phase."
        return tools, tool_names

    def _get_feature_info(self, state: State) -> str:  # 追踪数据（特征）流
        # Define file names for before and after the current phase
        phase_files = {
            "Preliminary Exploratory Data Analysis": ("train.csv", "test.csv", "train.csv", "test.csv"),
            "Data Cleaning": ("train.csv", "test.csv", "cleaned_train.csv", "cleaned_test.csv"),
            "In-depth Exploratory Data Analysis": ("cleaned_train.csv", "cleaned_test.csv", "cleaned_train.csv", "cleaned_test.csv"),
            "Feature Engineering": ("cleaned_train.csv", "cleaned_test.csv", "processed_train.csv", "processed_test.csv"),
            "Model Building, Validation, and Prediction": ("processed_train.csv", "processed_test.csv", "processed_train.csv", "processed_test.csv"),
            "PEDA Insight Extraction": ("train.csv", "test.csv", "train.csv", "test.csv"),
            "IEDA Insight Extraction": ("cleaned_train.csv", "cleaned_test.csv", "cleaned_train.csv", "cleaned_test.csv")
        }

        before_train, before_test, after_train, after_test = phase_files.get(state.phase, (None, None, None, None))

        if before_train is None:
            raise ValueError(f"Unknown phase: {state.phase}")

        # Read the datasets
        before_train_df = pd.read_csv(f'{state.competition_dir}/{before_train}')
        before_test_df = pd.read_csv(f'{state.competition_dir}/{before_test}')
        after_train_df = pd.read_csv(f'{state.competition_dir}/{after_train}')
        after_test_df = pd.read_csv(f'{state.competition_dir}/{after_test}')

        # Get features before and after
        features_before = list(before_train_df.columns)
        features_after = list(after_train_df.columns)

        # Identify target variable  识别目标变量 测试集一般不包含目标变量 因此训练集变量去掉测试集变量就是目标变量 （不一定吧，时序预测就有目标列）
        target_variable = list(set(features_after) - set(after_test_df.columns))

        if len(target_variable) == 1:
            target_variable = target_variable[0]
        elif len(target_variable) > 1:
            logging.warning(f"Multiple potential target variables found: {target_variable}")
            target_variable = ', '.join(target_variable)
        else:
            logging.warning("No target variable found by comparing train and test columns")
            target_variable = "Unknown"

        feature_info = PROMPT_FEATURE_INFO.format(  # 只返回训练集的数据特征变化。
            target_variable=target_variable,
            features_before=features_before,
            features_after=features_after
        )
        return feature_info

    def action(self, state: State) -> Dict[str, Any]:  # 当前阶段某个Agent执行它的任务
        logger.info(f"State {state.phase} - Agent {self.role} is executing.")
        role_prompt = AGENT_ROLE_TEMPLATE.format(agent_role=self.role)
        return self._execute(state, role_prompt)

    def _execute(self, state: State, role_prompt: str) -> Dict[str, Any]:
        raise NotImplementedError("Subclasses should implement this!")
