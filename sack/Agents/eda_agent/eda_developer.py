from typing import Dict, Any, Tuple
import json
import re
import logging
import os
import copy
import subprocess
import shutil

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
from sack.Agents.agent_developer import Developer
from sack.state import State
from sack.Prompts.eda_prompt.prompt_developer import PROMPT_DEVELOPER_TASK_EDA, PROMPT_DEVELOPER_EDA
from sack.Prompts.prompt_developer import *


class EDADeveloper(Developer):
    def __init__(self, model: str, type: str):
        super().__init__(
            # role="developer",
            # description="You are skilled at writing code to call PREDEFINED EDA/ML tools according to plan, with strong debugging ability.",
            model=model,
            type=type
        )


    def _execute(self, state: State, role_prompt: str) -> Dict[str, Any]:
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
        task = PROMPT_DEVELOPER_TASK_EDA
        constraints = PROMPT_DEVELOPER_CONSTRAINTS.format(restore_path=restore_path, competition_path=competition_path, phase_name=state.phase)
        background_info = state.background_info
        state_info = state.get_state_info()

        plan = state.memory[-1]["planner"]["plan"]

        # 初始化系统提示（强化工具调用）
        history.append({
            "role": "system",
            "content": f"{role_prompt}You MUST call ONLY predefined EDA tools (no custom implementation) to complete the plan. {self.description} "
                       f"When you are writing code, you should follow the following constraints.\n{constraints}"
        })

        if len(state.memory) != 1:
            self.description = "You are skilled at writing and implementing code according to plan by calling predefined tools." \
                               "You have advanced reasoning abilities and can improve your answers through reflection."
            experience_with_suggestion = self._gather_experience_with_suggestion(state)

        # 多轮生成/调试逻辑（保留核心流程）
        while round <= max_tries:
            if round == 0 or retry_flag or no_code_flag:
                if len(state.memory) == 1:
                    # 第一轮没有经验，生成代码。
                    input = PROMPT_DEVELOPER_EDA.format(
                        phases_in_context=state.context, phase_name=state.phase,
                        state_info=state_info, background_info=background_info, plan=plan, task=task
                    )
                    if retry_flag or no_code_flag:
                        history = history[:1]
                    raw_reply, history = self.llm.generate(input, history, max_completion_tokens=4096)

                    # 补充工具/代码上下文
                    prompt_round1 = self._generate_prompt_round1(state)
                    raw_reply, history = self.llm.generate(prompt_round1, history, max_completion_tokens=4096)
                else:
                    # 后续轮次：注入经验
                    input = PROMPT_DEVELOPER_WITH_EXPERIENCE_ROUND0_0.format(
                        phases_in_context=state.context, phase_name=state.phase,
                        state_info=state_info, background_info=background_info, plan=plan,
                        task=task, experience_with_suggestion=experience_with_suggestion
                    )
                    raw_reply, history = self.llm.generate(input, history, max_completion_tokens=4096)

                    prompt_round0 = self._generate_prompt_round1(state)
                    raw_reply, history = self.llm.generate(prompt_round0, history, max_completion_tokens=4096)
                    with open(f'{state.restore_dir}/{self.role}_first_mid_reply.txt', 'w', encoding='utf-8') as f:
                        f.write(raw_reply)

                    input = PROMPT_DEVELOPER_WITH_EXPERIENCE_ROUND0_2
                    raw_reply, history = self.llm.generate(input, history, max_completion_tokens=4096)

                # 保存生成结果
                if retry_flag:
                    self._save_all_error_messages(state)
                    self.all_error_messages = []
                    logger.info("The developer asks for help when debugging the code. Regenerating the code.")
                    with open(f'{state.restore_dir}/{self.role}_retry_reply.txt', 'w', encoding='utf-8') as f:
                        f.write(raw_reply)
                elif no_code_flag:
                    self._save_all_error_messages(state)
                    self.all_error_messages = []
                    logger.info("Last reply has no code. Regenerating the code.")
                    with open(f'{state.restore_dir}/{self.role}_no_code_reply.txt', 'w', encoding='utf-8') as f:
                        f.write(raw_reply)
                else:
                    with open(f'{state.restore_dir}/{self.role}_first_reply.txt', 'w', encoding='utf-8') as f:
                        f.write(raw_reply)
                retry_flag = False

            elif round >= 1:
                # 调试分支
                if error_flag and round < max_tries:
                    raw_reply, single_round_debug_history = self._debug_code(
                        state, error_flag, not_pass_flag, not_pass_information, raw_reply
                    )
                    debug_history.append(single_round_debug_history)
                    if raw_reply == "HELP":
                        logger.info("The developer asks for help when debugging the code. Regenerating the code.")
                        retry_flag = True
                elif not error_flag:
                    # 单元测试分支
                    while test_round < 2 * max_tries and not error_flag:
                        logger.info(f"Start the {test_round+1}-th unit test.")
                        not_pass_flag, not_pass_information = self._conduct_unit_test(state)
                        if not_pass_flag:
                            raw_reply, single_round_test_history = self._debug_code(
                                state, error_flag, not_pass_flag, not_pass_information, raw_reply
                            )
                            test_history.append(single_round_test_history)
                            no_code_flag, _, path_to_run_code = self._generate_code_file(state, raw_reply)
                            error_flag = self._run_code(state, no_code_flag, path_to_run_code)
                        else:
                            break
                        test_round += 1
                    if not not_pass_flag or test_round == max_tries:
                        break
                else:
                    break

            # 执行代码生成/运行
            logger.info(f"The {round+1}-th try.")
            if retry_flag:
                round -= 1
            else:
                no_code_flag, _, path_to_run_code = self._generate_code_file(state, raw_reply)
                error_flag = self._run_code(state, no_code_flag, path_to_run_code)
            round += 1

        # 保存历史
        with open(f'{state.restore_dir}/{self.role}_history.json', 'w', encoding='utf-8') as f:
            json.dump(history, f, ensure_ascii=False, indent=4)
        with open(f'{state.restore_dir}/debug_history.json', 'w', encoding='utf-8') as f:
            json.dump(debug_history, f, ensure_ascii=False, indent=4)
        with open(f'{state.restore_dir}/test_history.json', 'w', encoding='utf-8') as f:
            json.dump(test_history, f, ensure_ascii=False, indent=4)

        # 保存历史
        execution_flag = True
        error_file = f'{state.restore_dir}/{state.dir_name}_error.txt'
        if os.path.exists(error_file):
            execution_flag = False
            logger.info(f"State {state.phase} - Agent {self.role} finishes working with error.")
        else:
            if not_pass_flag:
                execution_flag = False
                logger.info(f"State {state.phase} - Agent {self.role} finishes working with not pass tests.")
                with open(f'{state.restore_dir}/{state.dir_name}_not_pass_information.txt', 'w', encoding='utf-8') as f:
                    f.write(not_pass_information)
            else:
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
