import os
import pandas as pd
import json
import re
import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

from sack.LLMComponent.llm import OpenaiEmbeddings, LLM
from sack.state import State
from sack.utils import load_config
from sack.Prompts.prompt_developer import *

class DebugTool: # 璋冭瘯宸ュ叿
    def __init__(
        self,
        model: str = 'qwen3-coder-plus',
        type: str = 'api'       
    ):
        self.llm = LLM(model, type)

    # 带着代码运行错误来调试，让llm根据错误信息定位错误段
    def debug_code_with_error(self, state: State, all_error_messages: list, output_messages: str, previous_code: str, wrong_code: str, error_messages: str, tools: str, tool_names: list) -> str:
        debug_times = len(all_error_messages)
        logger.info(f"Debug times: {debug_times}") # debug娆℃暟

        single_round_debug_history = [] # 淇濆瓨debug杩囩▼
        # locate error 提示拿着error信息寻找错误代码片段（只需要定位归因  不修正）
        input = PROMPT_DEVELOPER_DEBUG_LOCATE.format(  # 鎻愪緵涔嬪墠鐨勪唬鐮侊紝褰撳墠閿欒浠ｇ爜锛岄敊璇俊鎭互鍙婁唬鐮佺殑杈撳嚭
            previous_code=previous_code,
            wrong_code=wrong_code,
            error_messages=error_messages,
            output_messages=output_messages
        )

        # 杩欓噷涓轰粈涔堣寮鸿鎷嗘垚瑕佸伐鍏峰啀瀹氫綅閿欒鐨勪袱姝ユ搷浣滐紵
        _, locate_history = self.llm.generate(input, [], max_completion_tokens=40960)
        input = f"# TOOL DESCRIPTIONS #\n{tools}" # 鎻愪緵宸ュ叿
        locate_reply, locate_history = self.llm.generate(input, locate_history, max_completion_tokens=40960) # 瀹氫綅閿欒
        single_round_debug_history.append(locate_history) # 瀹氫綅杩囩▼鐨刴emory淇濆瓨
        with open(f'{state.restore_dir}/debug_locate_error.txt', 'w',encoding="utf-8") as f:
            f.write(locate_reply)

        # 最多调试四次，所以当第3次调试时就要特殊处理：要分析过去两次调试是否有意义（相同错误是否重复出现），如果没有意义（相同错误一直没解决）就停止调试直接寻求帮助
        if debug_times >= 3:
            all_error_info = ""
            for i, error_message in enumerate(all_error_messages):
                all_error_info += f"This is the {i}-th error message:\n{error_message}\n ------------\n"
            input = PROMPT_DEVELOPER_DEBUG_ASK_FOR_HELP.format(i=debug_times, all_error_messages=all_error_info)
            help_reply, help_history = self.llm.generate(input, [], max_completion_tokens=40960)
            single_round_debug_history.append(help_history)
            with open(f'{state.restore_dir}/debug_ask_for_help.txt', 'w',encoding="utf-8") as f:
                f.write(help_reply)
            if any(keyword in help_reply for keyword in ["<HELP>", "</HELP>", "I need help", "need help"]):
                return "HELP", single_round_debug_history  # 濡傛灉鍒ゆ柇涓洪渶瑕佸府鍔╋紝灏辨棤闇€鍚庣画鐨勪慨澶嶉敊璇紝鐩存帴杩斿洖

        # extract code
        pattern = r"```python(.*?)```"
        error_code_matches = re.findall(pattern, locate_reply, re.DOTALL)
        try:
            most_relevant_code_snippet = error_code_matches[-1]
        except:
            most_relevant_code_snippet = "Can't find the most relevant code snippet."

        # fix bug 拿着错误信息、输出信息、使用的工具以及定位到的错误代码段（无需再拿其他代码）  修复错误
        input = PROMPT_DEVELOPER_DEBUG_FIX.format(
            most_relevant_code_snippet=most_relevant_code_snippet,
            error_messages=error_messages,
            output_messages=output_messages,
            tools=tools
        )
        fix_reply, fix_bug_history = self.llm.generate(input, [], max_completion_tokens=40960) # 包括分析原因和修正的代码段
        single_round_debug_history.append(fix_bug_history)
        with open(f'{state.restore_dir}/debug_fix_bug.txt', 'w',encoding='utf-8') as f:
            f.write(fix_reply)

        # extract code 从回答中提取代码段
        correct_code_matches = re.findall(pattern, fix_reply, re.DOTALL)
        code_snippet_after_correction = correct_code_matches[-1]

        # merge code  鎻愪緵閿欒浠ｇ爜锛岄敊璇唬鐮佹锛屼慨姝ｅ悗鐨勪唬鐮佹  鎶婁唬鐮佹鏇挎崲鍒板師閿欒浠ｇ爜浣嶇疆
        input = PROMPT_DEVELOPER_DEBUG_MERGE.format(
            wrong_code=wrong_code,
            most_relevant_code_snippet=most_relevant_code_snippet,
            code_snippet_after_correction=code_snippet_after_correction
        )
        merge_reply, merge_code_history = self.llm.generate(input, [], max_completion_tokens=40960)
        single_round_debug_history.append(merge_code_history)  # 合并后代码保存
        with open(f'{state.restore_dir}/debug_merge_code.txt', 'w',encoding="utf-8") as f:
            f.write(merge_reply)

        with open(f'{state.restore_dir}/single_round_debug_history.json', 'w',encoding="utf-8") as f:
            json.dump(single_round_debug_history, f,ensure_ascii=False, indent=4)

        return merge_reply, single_round_debug_history

    def debug_code_with_no_pass_test(self, state: State, output_messages: str, previous_code: str, code_with_problem: str, not_pass_information: str) -> str:
        single_round_test_history = []
        # locate error
        input = PROMPT_DEVELOPER_TEST_LOCATE.format(
            previous_code=previous_code,
            code_with_problem=code_with_problem,
            not_pass_information=not_pass_information,
            output_messages=output_messages
        )
        raw_reply, test_locate_history = self.llm.generate(input, [], max_completion_tokens=40960)
        input = PROMPT_DEVELOPER_TEST_REORGANIZE_LOCATE_ANSWER
        code_snippets_with_problem, test_locate_history = self.llm.generate(input, test_locate_history, max_completion_tokens=40960)
        single_round_test_history.append(test_locate_history)
        with open(f'{state.restore_dir}/test_locate_problem.txt', 'w',encoding="utf-8") as f:
            f.write(code_snippets_with_problem)

        # fix bug
        input = PROMPT_DEVELOPER_TEST_FIX.format(
            code_snippets_with_problem=code_snippets_with_problem,
            output_messages=output_messages,
            not_pass_information=not_pass_information
        )
        raw_reply, test_fix_history = self.llm.generate(input, [], max_completion_tokens=40960)
        with open(f'{state.restore_dir}/thought_to_test_fix_problem.txt', 'w',encoding="utf-8") as f:
            f.write(raw_reply)
        single_round_test_history.append(test_fix_history)
        input = PROMPT_DEVELOPER_TEST_REORGANIZE_FIX_ANSWER
        code_snippets_after_correction, test_fix_history = self.llm.generate(input, test_fix_history, max_completion_tokens=40960)
        with open(f'{state.restore_dir}/test_fix_problem.txt', 'w',encoding="utf-8") as f:
            f.write(code_snippets_after_correction)


        # merge code
        input = PROMPT_DEVELOPER_TEST_MERGE.format(
            code_with_problem=code_with_problem,
            code_snippets_with_problem=code_snippets_with_problem,
            code_snippets_after_correction=code_snippets_after_correction
        )
        raw_reply, merge_code_history = self.llm.generate(input, [], max_completion_tokens=40960)
        single_round_test_history.append(merge_code_history)
        with open(f'{state.restore_dir}/test_merge_code.txt', 'w',encoding="utf-8") as f:
            f.write(raw_reply)

        with open(f'{state.restore_dir}/single_round_test_history.json', 'w',encoding="utf-8") as f:
            json.dump(single_round_test_history, f,ensure_ascii=False, indent=4)

        return raw_reply, single_round_test_history
