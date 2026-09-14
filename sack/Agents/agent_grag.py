import json
import subprocess
import re
import logging
import os
from typing import Dict, List, Any
from sack.Prompts.prompt_graphrag import *
from sack.state import State
from sack.Agents.agent_base import Agent

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
class GraphRetriever(Agent):
    def __init__(self, model: str, type: str, knowledge_graph_path: str = "."):
        super().__init__(
            role="graph_retriever",
            description="Expert at using GraphRAG to enhance planning constraints with domain knowledge.",
            model=model,
            type=type
        )
        self.knowledge_graph_path = knowledge_graph_path


    def build_graphrag_query(self, current_phase:str,task_name: str) -> str:
        """Build a semantic GraphRAG query for the current task."""

        # 基础查询模板。
        base_query = PROMPT_QUERY.format(phase=current_phase,task_name=task_name)
        return re.sub(r'\s+', ' ', base_query).strip()

    def query_graphrag(self, query: str) -> List[str]:
        """Run a GraphRAG query and parse the returned constraints."""
        try:
            # 提取直到指定标记前的完整内容。
            question_end = query.find('?') + 1
            if question_end > 0:
                question_part = query[:question_end]
            else:
                # 如果没有问号，使用前50个字符
                question_part = query[:50] + "..."

            logger.info(f"Executing query: {question_part}")
            venv_cmd_path = r"C:\Users\A\AppData\Local\pypoetry\Cache\virtualenvs\graphrag-L9nqtZF1-py3.11\Scripts\graphrag.cmd"


            # 构建命令
            command = [
                venv_cmd_path,
                "query",
                "--root", self.knowledge_graph_path,
                "--method", "local",
                "--query", query
            ]

            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=True,
                encoding="utf-8"
            )
            return self.parse_rag_output(result.stdout)

        except subprocess.CalledProcessError as e:
            logger.info(f"GraphRAG execution failed: {e.stderr}")
            return []
        except Exception as e:
            logger.info(f"Unexpected error during query: {str(e)}")
            return []

    def parse_rag_output(self, output: str) -> List[str]:
        """Parse the constraint list returned by GraphRAG."""
        if not isinstance(output, str) or not output.strip():
            return []

        # 定位SUCCESS响应的起始位置
        success_marker = "SUCCESS: Local Search Response:"
        start_idx = output.find(success_marker)

        if start_idx == -1:
            logger.info("Error: No SUCCESS marker found")
            return []

        # 定位SUCCESS响应的起始位置
        response_content = output[start_idx + len(success_marker):].strip()
        response_content = re.sub(r'\x1b\[\d+m', '', response_content)   # 移除颜色代码

        # 提取方括号内的内容（处理可能未闭合的括号）
        list_start = response_content.find('[')
        list_end = response_content.rfind(']')  # 使用rfind找最后一个可能的右括号

        if list_start == -1:
            logger.info("Error: No opening bracket '[' found")
            return []

        # 若未找到结束标记，则读取到文本末尾。
        if list_end == -1:
            list_end = len(response_content) - 1

        list_content = response_content[list_start + 1:list_end].strip()

        # 如果没有找到闭合括号，假设内容到末尾
        constraints = []
        current_constraint = ""
        in_quote = False
        escape_next = False

        for char in list_content:
            if escape_next:
                current_constraint += char
                escape_next = False
                continue

            if char == '\\':
                escape_next = True
                continue

            if char == '"':
                in_quote = not in_quote
                if not in_quote and current_constraint.strip():
                    # 移除来源标记。
                    cleaned = re.sub(r'\[Data:.*?\]', '', current_constraint)
                    constraints.append(cleaned.strip())
                    current_constraint = ""
                continue

            if in_quote:
                current_constraint += char

        # 过滤无效约束
        return [c for c in constraints if c.strip()]



    def integrate_json_constraints(self, plan: List[Dict[str, Any]], domain_constraints: Dict[str, List[str]]) -> List[Dict[str, Any]]:
        """Use the LLM to integrate retrieved constraints into a JSON plan."""
        # 转换为紧凑 JSON 格式。
        original_plan_json = json.dumps(plan, ensure_ascii=False, separators=(',', ':'))
        constraints_json = json.dumps(domain_constraints, ensure_ascii=False, separators=(',', ':'))

        # 转换为紧凑JSON格式
        original_plan_json = original_plan_json.replace("{", "{{").replace("}", "}}")
        constraints_json = constraints_json.replace("{", "{{").replace("}", "}}")

        # 构建提示词
        input_prompt = PROMPT_INTEGRATE_CONSTRAINTS_JSON.format(
            json_plan=original_plan_json,
            grag_constraints=constraints_json
        )

        logger.info("Generating integrated plan with LLM...")

        # 构建提示词
        raw_response, _ = self.llm.generate(
            input_prompt,
            history=[],
            max_completion_tokens=4096
        )

        # 调用大模型
        try:
            parsed_data = self._parse_json(raw_response)
            logger.info("JSON parse successful")

            # 尝试使用自定义解析器解析
            if isinstance(parsed_data, dict):
                return parsed_data.get('final_answer', plan)
            elif isinstance(parsed_data, list):
                return parsed_data  # 直接返回列表
            else:
                logger.info(f"Unexpected parse type: {type(parsed_data)}")
                return plan

        except Exception as e:
            logger.info(f"Parse fail: {str(e)}")
            logger.info(f"Original response 100 character: {raw_response[:100]}...")

            # 解析失败时返回原始计划
            return plan

    def integrate_markdown_constraints(self, markdown_plan: str, domain_constraints: Dict[str, List[str]]) -> str:
        """Use the LLM to integrate retrieved constraints into a markdown plan."""
        original_plan_markdown = json.dumps(domain_constraints, ensure_ascii=False, indent=2)
        # 解析失败时返回原始计划
        input_prompt = PROMPT_INTEGRATE_CONSTRAINTS_MARKDOWN.format(
            markdown_plan=markdown_plan,
            grag_constraints=original_plan_markdown
        )

        logger.info("Generating integrated Markdown plan with LLM...")

        # 构建提示词
        raw_response, _ = self.llm.generate(
            input_prompt,
            history=[],
            max_completion_tokens=8192  # 增加 token 限制，以适配 Markdown 格式。
        )

        # 调用大模型
        if self._parse_markdown(raw_response):
            logger.info("Markdown format verification successful")
            return raw_response
        else:
            logger.info("Markdown format verification failed. Return to the original plan")
            return markdown_plan

    def _execute(self, state: State): # 此前直接将新约束插入计划的方式。
        """Load plan files, retrieve constraints, and write enriched plans."""
        json_plan_path = f'{state.restore_dir}/json_plan.json'
        markdown_plan_path = f'{state.restore_dir}/markdown_plan.txt'

        with open(json_plan_path, 'r', encoding='utf-8') as f:
            json_plan = json.load(f)

        with open(markdown_plan_path, 'r', encoding='utf-8') as f:
            markdown_plan = f.read()

        logger.info(f"Processing {len(json_plan)} tasks from plan")

        # 为每个任务检索约束
        domain_constraints = {}
        for task in json_plan:
            task_name = task["task"]
            query = self.build_graphrag_query(state.phase,task_name)
            constraints = self.query_graphrag(query)

            if constraints:
                domain_constraints[task_name] = constraints
                logger.info(f"Retrieved {len(constraints)} constraints for '{task_name}'")

        # 集成约束
        if domain_constraints:
            enriched_json_plan = self.integrate_json_constraints(json_plan, domain_constraints)
            # 保存增强后的计划
            output_path = f'{state.restore_dir}/grag_json_plan.json'
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(enriched_json_plan, f,ensure_ascii=False, indent=4)
            logger.info(f"Enriched json plan saved to {output_path}")

            enriched_markdown_plan = self.integrate_markdown_constraints(markdown_plan, domain_constraints)
            output_path = f'{state.restore_dir}/grag_markdown_plan.txt'
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(enriched_markdown_plan)
            logger.info(f"Enriched markdown plan saved to {output_path}")
            return enriched_json_plan, enriched_markdown_plan

        else:
            logger.info("No constraints retrieved, using original plan")
            return None, None



if __name__ == "__main__":


    import sys
    from pathlib import Path

    # 设置知识图谱路径和原始计划路径
    knowledge_graph_path = "D:/PythonProject/graphrag"  # 当前目录作为知识图谱根目录
    phase_path = "../data/competitions/3-test/pre_eda"

    # 设置知识图谱路径和原始计划路径
    if not Path(phase_path).exists():
        raise FileNotFoundError(f"Phase path does not exist: {phase_path}")

    # 创建GraphRetriever实例
    retriever = GraphRetriever(
        model="qwen2.5-14b-instruct",  # 指定使用的LLM模型
        type="api",  # 指定模型类型
        knowledge_graph_path=knowledge_graph_path
    )

    # 模拟State对象
    class MockState:
        def __init__(self, restore_dir):
            self.restore_dir = restore_dir
            self.phase="Preliminary Exploratory Data Analysis"

    # 设置恢复目录为计划文件所在目录
    restore_dir = str(phase_path)
    state = MockState(restore_dir)

    # 设置恢复目录为计划文件所在目录
    a,b= retriever._execute(state)
    print(a,b)


