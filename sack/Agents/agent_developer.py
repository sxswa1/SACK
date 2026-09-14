from typing import Dict, Any, Tuple
import json
import re
import logging
import os
import sys
import copy
import subprocess
import shutil
import pdb

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

from sack.Agents.agent_base import Agent
from sack.utils import read_file
from sack.state import State
from sack.Prompts.prompt_base import *
from sack.Prompts.prompt_developer import *

class Developer(Agent):
    def __init__(self, model: str, type: str):  
        super().__init__(
            role="developer",
            description="You are skilled at writing and implementing code according to plan.",
            model=model,
            type=type
        )
        self.all_error_messages = []

    def _is_previous_code(self, state: State) -> Tuple[bool, str, str,str]: # 提取前一相关阶段的代码，跳过 EDA 阶段。
        previous_phase = state.get_previous_phase()
        previous_dir_name = state.phase_to_directory[previous_phase]
        path_to_previous_code = f'{state.competition_dir}/{previous_dir_name}/{previous_dir_name}_code.py'
        path_to_previous_run_code = f'{state.competition_dir}/{previous_dir_name}/{previous_dir_name}_run_code.py'
        path_to_last_phase_code = f'{state.competition_dir}/{previous_dir_name}/single_phase_code.txt'
        return os.path.exists(path_to_previous_code), path_to_previous_code, path_to_previous_run_code, path_to_last_phase_code

    def _delete_output_in_code(self, state: State, previous_code) -> str:  # 删除所有包含绘图的for循环  以及print plt 其他绘图代码（这些代码段无法调试，需要去除后才能调试代码）
        previous_run_code = copy.deepcopy(previous_code) # deep copy to prevent modifying the original data
        keywords = ('sns.', '.plot', '.hist', '.plt') # 绘图代码的关键词。

        # first scan: identify for loops, replace the whole block
        for_loop_list = []  # 所有for循环的开始和结束行索引
        in_for_loop = False
        # pdb.set_trace()
        for i, line in enumerate(previous_run_code):
            if line.startswith('    for'): # 识别 for 循环。
                tmp_loop = []
                indent = line[:len(line) - len(line.lstrip())]  # 获取缩进部分。
                tmp_loop.append(i) # 记录 for 循环的起始行索引。
                in_for_loop = True
            elif in_for_loop and line.startswith(indent) and not line.startswith('    '+indent) and len(line.strip()) > 0:  # 跳出for循环后的一行
                tmp_loop.append(i) # record the end line of the for loop
                in_for_loop = False
                for_loop_list.append(tmp_loop)

        # reverse order replace for loops with '    pass'
        for start, end in for_loop_list[::-1]: # 从后往前 将所有包含绘图的for循环都替换成pass
            loop_code = "\n".join(previous_run_code[start:end])
            if any(keyword in loop_code for keyword in keywords):  # if the for loop contains keywords
                previous_run_code[start:end] = ['    pass\n']  # replace the corresponding lines

        # second scan: replace print and plt.show / plt.save lines, keep the indent
        start_signs = ('print', 'plt')
        for i, line in enumerate(previous_run_code): # 将 print、plt 及其他绘图语句替换为 pass。
            stripped_line = line.lstrip()
            if stripped_line.startswith(start_signs) or any(keyword in stripped_line for keyword in keywords):
                indent = line[:len(line) - len(stripped_line)]  # get the indent part
                previous_run_code[i] = indent + 'pass\n'
        
        # third scan: merge consecutive pass lines  如果有连续的pass 则合并
        new_code = []
        pass_found = False
        
        for line in previous_run_code:
            if line.strip() == 'pass':
                if not pass_found:  # first time encounter pass
                    new_code.append(line)
                    pass_found = True
            else:
                new_code.append(line)
                pass_found = False
        
        return new_code

    def _generate_code_file(self, state: State, raw_reply) -> Tuple[bool, str, str]:  # 把返回的代码生成代码文件，里边添加了import头，并把生成的代码封装成了函数
        is_previous_code, path_to_previous_code, _, _ = self._is_previous_code(state)
        previous_tools= []
        if is_previous_code: # 提取代码主体。
            with open(path_to_previous_code, 'r', encoding='utf-8') as f_1:
                previous_code = f_1.readlines()
                previous_code = previous_code[:-2] # delete the last two lines  这些是手动添加的execute代码段
                previous_phase= state.get_previous_phase(type='code') # 只返回一个阶段
                if state.phase != 'Model Building, Validation, and Prediction':
                    previous_tools = state.phase_to_ml_tools[previous_phase]
                else:
                    previous_previous_tools = state.phase_to_ml_tools["Data Cleaning"]
                    previous_tools = state.phase_to_ml_tools[previous_phase] + previous_previous_tools
                if len(previous_tools):
                    previous_code = previous_code[8+2+len(previous_tools):] # 这些是前缀import的代码段，剩下的就是前一个阶段生成的代码  有工具就是工具数+2行
                else:
                    previous_code = previous_code[8+1:] # 没有工具导入时，跳过一行空行。
            previous_run_code = self._delete_output_in_code(state, previous_code) # 删除 plt、print 等输出代码。
        else:
            previous_code = []
            previous_run_code = []
        # code with output
        path_to_code = f'{state.restore_dir}/{state.dir_name}_code.py'
        path_to_run_code = f'{state.restore_dir}/{state.dir_name}_run_code.py'

        no_code_flag = False
        # Extract code from the file
        pattern = r"```python(.*?)```"
        matches = re.findall(pattern, raw_reply, re.DOTALL)
        code_lines = []
        # pdb.set_trace()
        for match in matches:
            code_lines.extend(match.split('\n'))
        
        # Enclose the code in a function
        # 所有代码行缩进一个单位，从而可以放在预定义好的函数头里，把阶段代码封装成一个函数
        code_lines = [f"    {line}\n" for line in code_lines]
        if len(code_lines) == 0:
            logging.error("No code found in the reply.")
            # pdb.set_trace()
            no_code_flag = True
            return True, "no code", "no code"
        
        with open(f'{state.restore_dir}/single_phase_code.txt', 'w',encoding="utf-8") as f: # save the single phase code
            f.write("\n".join(matches)) # 将开发智能体生成的代码保存到 single_phase_code.txt。
        tools_list = state.ml_tools.copy() # 当前阶段的工具
        import_section = ""
        if state.phase in ["Data Cleaning"]:
            import_section = "from Tools.ml_tools import (\n    " + ",\n    ".join(tools_list) + ",\n)"
        elif state.phase in ["In-depth Exploratory Data Analysis","Feature Engineering","Model Building, Validation, and Prediction"]:
            tools_list.extend(previous_tools) 
            import_section = "from Tools.ml_tools import (\n    " + ",\n    ".join(tools_list) + ",\n)"
        elif state.phase in ['PEDA Insight Extraction','IEDA Insight Extraction']:  # 仅在 GetEDAInsight 模式下获取 EDA 工具。
            import_section = "from Tools.eda_tools import (\n    " + ",\n    ".join(tools_list) + ",\n)"
            if state.phase == 'IEDA Insight Extraction':  
                previous_import_section ="from Tools.ml_tools import (\n    " + ",\n    ".join(previous_tools) + ",\n)"# 数据清理阶段的import也要加进来
                import_section = import_section +"\n"+ previous_import_section  # 两个 import 片段来自不同 Python 文件，分别拼接导入。
        prefix_in_code_file = [line + '\n' for line in PREFIX_IN_CODE_FILE.format(import_section=import_section).split('\n')]
        code_with_output_lines = prefix_in_code_file + previous_code + code_lines # 拼接前一个阶段的代码和当前阶段的代码，统一放在一个函数头下组成同一个函数（保留了输出行）
        run_code_lines = prefix_in_code_file + previous_run_code + code_lines # 拼接前一阶段去除输出后的代码和当前阶段代码。

        # Write the code to a python file
        # 把生成的可执行代码保存
        with open(path_to_code, 'w', encoding='utf-8') as f_w:
            f_w.write("".join(code_with_output_lines))
            f_w.write('\n\nif __name__ == "__main__":\n    generated_code_function()')  # 添加execute代码段
        # Write the run code to a python file
        with open(path_to_run_code, 'w', encoding='utf-8') as f_w:
            f_w.write("".join(run_code_lines))
            f_w.write('\n\nif __name__ == "__main__":\n    generated_code_function()')# 添加execute代码段
        
        return no_code_flag, path_to_code, path_to_run_code

    def _run_code(self, state: State, no_code_flag: bool, path_to_run_code: str) -> str: # 执行代码
        # Delete previous images files
        if 'eda' in state.restore_dir: # 如果当前阶段是EDA，有代码对应图片存在本地，要先删除所有已存储图片以及文件夹
            images_dir = f'{state.restore_dir}/images/'
            for filename in os.listdir(images_dir):
                image_path = os.path.join(images_dir, filename)
                try:
                    if os.path.isfile(image_path) or os.path.islink(image_path):
                        os.remove(image_path)  # Delete file
                    elif os.path.isdir(image_path):
                        shutil.rmtree(image_path)  # Delete directory
                except Exception as e:
                    logger.info(f"Failed to delete {image_path}. Reason: {e}")
            logger.info(f"All files in directory '{images_dir}' have been deleted successfully.")

        # Run the code
        timeout_flag = False
        error_flag = False
        path_to_error = f'{state.restore_dir}/{state.dir_name}_error.txt'
        path_to_output = f'{state.restore_dir}/{state.dir_name}_output.txt'

        if no_code_flag: # 如果没有代码，要把没有代码的错误添加到error记录里
            with open(path_to_error, 'w', encoding='utf-8') as f:
                f.write("No code found in the reply.")
            with open(path_to_output, 'w', encoding='utf-8') as f:
                f.write("") # 清空输出文件。
            return True # error_flag

        result = {}
        # timeout  这不是永远都会执行吗？
        if 'Analysis' in state.phase: # EDA 阶段。
            timeout = 1200
            timeout_info = "Your code is running out of time, please consider resource availability and reduce the number of data analysis plots drawn."
        elif 'Model' in state.phase: # 模型构建阶段。
            timeout = 28800  # 原来是2400
            timeout_info = "Your code is running out of time, please consider resource availability and try fewer models."
        else: # 其他阶段。
            timeout = 3600
            timeout_info = "Your code is running out of time, please consider resource availability or other factors."
        try:
            result = subprocess.run([sys.executable, '-W', 'ignore', path_to_run_code],
                                    capture_output=True, text=True, timeout=timeout,encoding='utf-8'
                                   ) # 执行代码  preexec_fn=os.setsid适用于unix  windows似乎不需要  windows系统用python linux用python3
        except subprocess.TimeoutExpired:  # 记录超时错误。
            logger.info("Code execution timed out.")
            self.all_error_messages.append(timeout_info)
            with open(path_to_error, 'w', encoding='utf-8') as f:
                f.write(timeout_info)
            with open(path_to_output, 'w', encoding='utf-8') as f:
                f.write("")
            error_flag = True
        except subprocess.CalledProcessError as e:
            if e.returncode < 0: # 表示函数执行被操作系统的信号终止
                # Negative return codes usually indicate termination by a signal
                logger.info(f"Process was killed by signal {-e.returncode}")
                error_message = f"Process was terminated by the operating system (signal {-e.returncode})"
            else: # 进程异常终止时，保存错误信息。
                logger.info(f"Process exited with non-zero status: {e.returncode}")
                error_message = f"Process exited with status {e.returncode}: {e.stderr}"
            self.all_error_messages.append(error_message)
            with open(path_to_error, 'w', encoding='utf-8') as f:
                f.write(error_message+"\nI suggest you use logging module to record the information, which can help you find the reason why operation system terminated your process.\nOne possible reason is When working with dataframe-type data, you perform multiplication operations on different types of data.")
            error_flag = True
        else:  # 表示有正常错误发生，保存错误信息
            if result.returncode != 0: # 正常执行但返回错误
                logger.info(f"Process exited with non-zero status: {result.returncode}")
                error_message = f"Process exited with status {result.returncode}: {result.stderr}"
                self.all_error_messages.append(error_message)
                with open(path_to_error, 'w', encoding='utf-8') as f:
                    f.write(error_message)
                error_flag = True
            else: # 正常执行
                logger.info("Code executed successfully without errors.")
                self._save_all_error_messages(state)
                self.all_error_messages = []
                try:
                    os.remove(path_to_error) # 执行成功就要删除错误文件
                    logger.info(f"File '{path_to_error}' has been deleted successfully.")
                except FileNotFoundError:
                    logger.info(f"File '{path_to_error}' doesn't exist, you don't need to delete it.")

        # Write the output to a file
        if result and hasattr(result, 'stdout'):
            with open(path_to_output, 'w',encoding='utf-8') as f:
                f.write(result.stdout) # 记录执行输出
        else:
            with open(path_to_output, 'w',encoding='utf-8') as f:
                f.write("")

        return error_flag
    
    def _save_all_error_messages(self, state: State): # 保存运行后的所有错误信息
        if self.all_error_messages:
            base_filename = f'{state.restore_dir}/all_error_messages.txt'
            filename = base_filename
            counter = 1

            while os.path.exists(filename):
                filename = f'{state.restore_dir}/all_error_messages_{counter}.txt'
                counter += 1

            with open(filename, 'w', encoding='utf-8') as f:
                for i, message in enumerate(self.all_error_messages):
                    f.write(f"Message {i+1}:\n{message}\n\n\n")
            
            logger.info(f"All error messages saved to {filename}")

    def _conduct_unit_test(self, state: State) -> None:  #执行单元测试
        from sack.Tools.unit_test import TestTool

        test_tool = TestTool(tools_kb=None, model=self.model, type='api')
        not_pass_flag = False
        not_pass_tests = test_tool.execute_tests(state) # [(test1_number, test1_information), ...] if all pass return []
        logger.info(f"There are {len(not_pass_tests)} not pass tests.")
        not_pass_information = ""
        if not_pass_tests:
            not_pass_flag = True
            logger.info("Unit tests failed.")
            for test_flag, test_number, test_information in not_pass_tests:
                logger.info(f"Test {test_number}: {test_information}")
                not_pass_information += f"\n## TEST CASE NUMBER {test_number} ##\n{test_information}"
            # print("Not pass information: ", not_pass_information)
        else:
            not_pass_information = ""
            logger.info("All unit tests passed.")
            try:
                # Delete error file.
                path_to_not_pass_info = f'{state.restore_dir}/{state.dir_name}_not_pass_information.txt'
                os.remove(path_to_not_pass_info)
                logger.info(f"File '{path_to_not_pass_info}' has been deleted successfully.")
            except FileNotFoundError:
                logger.info(f"File '{path_to_not_pass_info}' doesn't exist, you don't need to delete it.")
        return not_pass_flag, not_pass_information

    def _debug_code(self, state: State, error_flag: bool, not_pass_flag: bool, not_pass_information: str, raw_reply: str) -> str: # 出现错误调试代码，寻找错误原因
        from sack.Tools.debug import DebugTool

        # prepare debug information, and then debug
        is_previous_code, path_to_previous_code, _, path_to_last_phase_code = self._is_previous_code(state) # 获取前一相关阶段的代码。
        if is_previous_code:# 如果前一相关阶段有代码。
            previous_code = read_file(path_to_last_phase_code) # 上一阶段的所有代码
        else:
            previous_code = "There is no code file in the previous phase."
        # Extract code from the file
        pattern = r"```python(.*?)```" # 解析python代码段
        matches = re.findall(pattern, raw_reply, re.DOTALL)  # 换行符也会被匹配到
        code_lines = []
        for match in matches:
            code_lines.extend(match.split('\n'))
        wrong_code = "\n".join(code_lines) # 合并后的待调试代码。
        # read error and output
        path_to_error = f'{state.restore_dir}/{state.dir_name}_error.txt' # 当前阶段的代码错误
        path_to_output = f'{state.restore_dir}/{state.dir_name}_output.txt' # 当前阶段的输出错误代码
        if os.path.exists(path_to_error): # 当前阶段过往存在的错误
            error_messages = read_file(path_to_error)
            if len(error_messages) > 10000:  # 错误代码太长 只保留10000个字符
                error_messages = error_messages[:10000] # truncate the error messages
                logger.info(f"The error messages are truncated to 10000 characters.")
                with open(f'{state.restore_dir}/{state.dir_name}_error_truncated.txt', 'w',encoding='utf-8') as f:
                    f.write(error_messages)
        else:
            error_messages = "There is no error message in the previous phase."
        if state.phase in ['Feature Engineering', 'Model Building, Validation, and Prediction']: # 特征工程和建模阶段额外读取执行输出，供调试使用。
            output_messages = read_file(path_to_output) # 读取代码执行输出
        else:
            output_messages = ""

        logger.info("Start debugging the code.")
        debug_tool = DebugTool(model='qwen3-coder-plus', type='api')
        if error_flag: # 带着执行错误去debug
            tools, tool_names = self._get_tools(state)
            reply, single_round_debug_history = debug_tool.debug_code_with_error(state, copy.deepcopy(self.all_error_messages), output_messages, previous_code, wrong_code, error_messages, tools, tool_names)
        elif not_pass_flag:
            reply, single_round_debug_history = debug_tool.debug_code_with_no_pass_test(state, output_messages, previous_code, wrong_code, not_pass_information)

        return reply, single_round_debug_history

    def _generate_prompt_round1(self, state: State) -> str: # 为开发智能体准备前一阶段代码、数据特征和可用工具。
        prompt_round1 = ""
        # read the code from the previous phase
        is_previous_code, path_to_previous_code, _, path_to_last_phase_code = self._is_previous_code(state)
        if is_previous_code: # 如果前一相关阶段有代码。
            previous_code = read_file(path_to_last_phase_code) # 读取所有阶段代码
        else:
            previous_code = "There is no code file in the previous phase."
        prompt_round1 += f"\n#############\n# CODE FROM PREVIOUS PHASE #\n{previous_code}"
        prompt_round1 += self._read_data(state, num_lines=1) # 读取数据样例，展示各个特征。
        tools, tool_names = self._get_tools(state) # 拿到这该阶段的所有工具
        if len(tool_names) > 0:
            prompt_round1 += PROMPT_AVAILABLE_TOOLS.format(tools=tools, tool_names=tool_names)
        else:
            prompt_round1 += "# AVAILABLE TOOLS #\nThere is no pre-defined Tools in this phase. You can use the functions from public libraries such as Pandas, NumPy, Scikit-learn, etc.\n"  # 没有预定义工具。

        return prompt_round1


    def _execute(self, state: State, role_prompt: str) -> Dict[str, Any]:
        # implement the development and debugging function
        history = []
        debug_history = []
        test_history = []
        self.all_error_messages = []
        round = 0
        test_round = 0
        max_tries = 5
        error_flag = False
        not_pass_flag = False
        no_code_flag = False
        retry_flag = False
        not_pass_information = ""
        restore_path = state.restore_dir
        competition_path = state.competition_dir
        task = PROMPT_DEVELOPER_TASK
        constraints = PROMPT_DEVELOPER_CONSTRAINTS.format(restore_path=restore_path, competition_path=competition_path, phase_name=state.phase) # 代码开发约束，包括可用数据路径和结果保存路径。
        # eda_support = ""
        # if "Exploratory Data Analysis" in state.phase:  # 暂停使用此 EDA 提示词分支。
        #     eda_support = PROMPT_EDA_DEVELOPER_SUPPORT
        background_info = state.background_info
        state_info = state.get_state_info()
        if state.phase == "Data Preparation":
            state_info+= PROMPT_DATA_PREPARATION_SUPPLEMENT

        plan = state.memory[-1]["planner"]["plan"] # 从当前阶段本轮记忆中获取 Markdown 格式的计划。

        history.append({"role": "system",
                        "content": f"{role_prompt}{self.description}\n when you are writing code, you should follow the plan and the following constraints.\n{constraints}"})

        if len(state.memory) != 1: # 非首轮执行时，读取已有经验。
            self.description = "You are skilled at writing and implementing code according to plan." \
                            "You have advanced reasoning abilities and can improve your answers through reflection."
            experience_with_suggestion = self._gather_experience_with_suggestion(state)


        # 获取 SACKCaseRetriever，检索代码片段。
        if state.use_mode=="DSPipeline" and state.phase !="Data Preparation":
            try:
                # 复用与 Planner 相同的检索器配置。
                sack_case_retriever = self.get_sack_case_retriever()
                if sack_case_retriever is None:
                    raise RuntimeError("SACKCaseRetriever is unavailable")
                # 检索计划中各任务对应的代码片段。
                task_code_mapping = sack_case_retriever.get_code_snippets_for_plan(plan=plan)
            except Exception as e:
                logger.warning("SACKCaseRetriever failed: %s", e)
                task_code_mapping = {}
        else:
            task_code_mapping = {}

        # 格式化代码段为提示词内容（与之前逻辑一致） TODO:这里只提供实施见解的代码段，没有保留上下文信息，可能会性能下降
        relevant_code_snippets = ""
        for step, data in task_code_mapping.items():
            relevant_code_snippets += f"## TASK {step}: {data['task_desc']}\n"
            # 遍历当前任务的各条见解。
            for idx, ins_data in enumerate(data["insights"], 1):
                relevant_code_snippets += f"### Reference Insights {idx}: {ins_data['source']}\n"
                # relevant_code_snippets += f" Insight URI: {ins_data['insight_uri']}\n"
                relevant_code_snippets += "Code snippets: \n"
                if ins_data["code_snippets"]!=None:# 能找到对应的实施代码(一般没有产生幻觉的话都能找到对应的代码段，产生幻觉的话就不参考代码段了)
                    for snippet in ins_data["code_snippets"]:
                        relevant_code_snippets += f"[{snippet['order']['value']}] {snippet['code_text']['value']}\n"
                else:
                    print(f"Code snippets not found.")
                    relevant_code_snippets += "Code snippet was not found."
                relevant_code_snippets += "\n"  # 分隔不同见解的代码段
            relevant_code_snippets += "---\n"  # 分隔不同任务。

        if not relevant_code_snippets:
            relevant_code_snippets = "No relevant code snippets available for reference.\n"

        while round <= max_tries: # 某阶段某轮次内部的 代码生成与调试的多次迭代
            if round == 0 or retry_flag or no_code_flag: # 代码生成分支   第一次/要重新代码生成/没有代码都需要生成代码
                if len(state.memory) == 1: # 第一轮没有经验
                    # round 0 竞赛背景 阶段任务要求  数据集信息  plan  任务（根据plan编码）
                    # 提示词中明确要求要对plan中的每个任务都要解释思考过程 编码 并解释代码
                    # 要求开发智能体获取前一阶段代码、数据特征和可用工具。
                    # input = PROMPT_DEVELOPER.format(phases_in_context=state.context, phase_name=state.phase, state_info=state_info, background_info=background_info, plan=plan,relevant_code_snippets= relevant_code_snippets,task=task,eda_support=eda_support)
                    input = PROMPT_DEVELOPER.format(phases_in_context=state.context, phase_name=state.phase, state_info=state_info, background_info=background_info, plan=plan,relevant_code_snippets= relevant_code_snippets,task=task)
                    if retry_flag or no_code_flag: # 需要重试或未生成代码时，将短期对话历史重置到系统提示词。
                        history = history[:1]
                    raw_reply, history = self.llm.generate(input, history, max_completion_tokens=40960)
                    # round 1  给他配备前一阶段代码 特征 和工具  他就可以开始根据plan完成任务生成代码了
                    prompt_round1 = self._generate_prompt_round1(state)
                    input = prompt_round1
                    raw_reply, history = self.llm.generate(input, history, max_completion_tokens=40960)
                else: # 后续轮次引入已有经验，不保留过去迭代的短期对话历史。
                    # round 0：注入已有经验。
                    input = PROMPT_DEVELOPER_WITH_EXPERIENCE_ROUND0_0.format(phases_in_context=state.context, phase_name=state.phase, state_info=state_info, background_info=background_info, plan=plan, task=task, experience_with_suggestion=experience_with_suggestion)
                    raw_reply, history = self.llm.generate(input, history, max_completion_tokens=40960)
                    # round 1 给他配备前一阶段代码 特征 和工具  他要先分析经验和建议
                    prompt_round0 = self._generate_prompt_round1(state)
                    input = prompt_round0
                    raw_reply, history = self.llm.generate(input, history, max_completion_tokens=40960)
                    with open(f'{state.restore_dir}/{self.role}_first_mid_reply.txt', 'w',encoding='utf-8') as f:
                        f.write(raw_reply)
                    # round 2：生成新的代码方案。
                    input = PROMPT_DEVELOPER_WITH_EXPERIENCE_ROUND0_2
                    raw_reply, history = self.llm.generate(input, history, max_completion_tokens=40960)
                if retry_flag: # 重试生成代码后，保存此前的错误信息并清空当前错误记录。
                    self._save_all_error_messages(state)
                    self.all_error_messages = [] # clear the error messages after retry
                    logger.info("The developer asks for help when debugging the code. Regenerating the code.")
                    with open(f'{state.restore_dir}/{self.role}_retry_reply.txt', 'w',encoding='utf-8') as f:
                        f.write(raw_reply) # 重新生成的代码入库
                elif no_code_flag: # 未生成代码。
                    self._save_all_error_messages(state)
                    self.all_error_messages = [] # clear the error messages
                    logger.info("Last reply has no code. Regenerating the code.")
                    with open(f'{state.restore_dir}/{self.role}_no_code_reply.txt', 'w',encoding='utf-8') as f:
                        f.write(raw_reply)
                else:
                    with open(f'{state.restore_dir}/{self.role}_first_reply.txt', 'w',encoding='utf-8') as f:
                        f.write(raw_reply)
                retry_flag = False
            elif round >= 1: # 代码调试与测试分支  第二次及之后每一次迭代如果有bug都要debug调试代码 （第一次只生成不调试） 如果没有bug就进行单元测试
                if error_flag and round < max_tries: # if there is still error in the last round, do not debug  存在错误时进行调试。
                    # debug in each round
                    raw_reply, single_round_debug_history = self._debug_code(state, error_flag, not_pass_flag, not_pass_information, raw_reply)
                    debug_history.append(single_round_debug_history)
                    if raw_reply == "HELP": # 如果它debug后无法解决错误 则需要重新生成代码
                        logger.info("The developer asks for help when debugging the code. Regenerating the code.")
                        retry_flag = True
                elif not error_flag: # if there is no error 没有bug就继续单元测试，单元测试要直接尝试到上限再推出
                    # conduct unit test
                    while test_round < 2*max_tries and not error_flag: # 重复测试和修复代码，直到通过测试或达到循环上限。
                        logger.info(f"Start the {test_round+1}-th unit test.")
                        not_pass_flag, not_pass_information = self._conduct_unit_test(state)
                        if not_pass_flag: # if the unit test is not passed 单元测试没通过也要debug问题所在 并修正对应代码段
                            raw_reply, single_round_test_history = self._debug_code(state, error_flag, not_pass_flag, not_pass_information, raw_reply)
                            test_history.append(single_round_test_history)
                            no_code_flag, _, path_to_run_code = self._generate_code_file(state, raw_reply) # 重新生成代码文件，保存修复后的代码。
                            error_flag = self._run_code(state, no_code_flag, path_to_run_code) # 执行代码并保存错误原因或正确输出
                        else: # 通过单元测试就可以跳出循环 可以进入下一阶段了
                            break
                        test_round += 1
                    if not not_pass_flag or test_round == max_tries: # 测试通过或达到此处的轮次条件时，退出当前代码迭代。
                        break
                else: # 代码仍有错误且调试达到上限时，退出当前代码迭代。
                    break
            logger.info(f"The {round+1}-th try.")
            if retry_flag: # 重新生成代码的轮次可以让round不变（这里-1后+1）
                round -= 1
            else: # 没有标识retry 说明代码已经生成了
                no_code_flag, _, path_to_run_code = self._generate_code_file(state, raw_reply) # 生成可执行代码
                error_flag = self._run_code(state, no_code_flag, path_to_run_code) # 执行代码
            round += 1

        # save history 某阶段的本轮结束了，开始存档
        with open(f'{state.restore_dir}/{self.role}_history.json', 'w',encoding='utf-8') as f:
            json.dump(history, f,ensure_ascii=False, indent=4)
        with open(f'{state.restore_dir}/debug_history.json', 'w',encoding='utf-8') as f:
            json.dump(debug_history, f,ensure_ascii=False, indent=4)
        with open(f'{state.restore_dir}/test_history.json', 'w',encoding='utf-8') as f:
            json.dump(test_history, f,ensure_ascii=False, indent=4)

        execution_flag = True
        if os.path.exists(f'{state.restore_dir}/{state.dir_name}_error.txt'): # 当前代码仍有错误（因为如果代码运行没有错误，会把过去的error记录删除）
            execution_flag = False
            logger.info(f"State {state.phase} - Agent {self.role} finishes working with error.")
        else:
            if not_pass_flag:# 没有执行错误记录但测试未通过，说明代码运行成功而单元测试失败。
                execution_flag = False
                logger.info(f"State {state.phase} - Agent {self.role} finishes working with not pass tests.")
                with open(f'{state.restore_dir}/{state.dir_name}_not_pass_information.txt', 'w',encoding='utf-8') as f:
                    f.write(not_pass_information)
            else: # 单元测试也通过了
                logger.info(f"State {state.phase} - Agent {self.role} finishes working.")

        input_used_in_review = f"   <background_info>\n{background_info}\n    </background_info>\n   <plan>\n{plan}\n    </plan>"
        return {
            self.role: {
                "history": history,
                "role": self.role,
                "description": self.description,
                "task": task,
                "input": input_used_in_review,
                "result": raw_reply,
                "status": execution_flag
            }
        }
    
