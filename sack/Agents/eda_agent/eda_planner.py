from typing import Dict, List, Any
import json
import re
import logging
import os
import ast
from builtins import input as builtin_input

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
from sack.Agents.agent_planner import Planner
from sack.Prompts.eda_prompt.prompt_planner import *
from sack.utils import read_file
from sack.state import State
from sack.paths import SACK_CONFIG_PATH
from sack.Prompts.prompt_base import *


class EDAPlanner(Planner):
    def __init__(self, model: str, type: str):
        super().__init__(
            # role="planner",
            # description="You are specialized in planning comprehensive exploratory data analysis tasks for EDAInsight extraction.",
            model=model,
            type=type
        )


    def _execute(self, state: State, role_prompt: str) -> Dict[str, Any]:
        """Run the EDA planner for the current state."""
        history = []
        data_preview = self._data_preview(state, num_lines=11)
        background_info = f"Data preview:\n{data_preview}"
        state.set_background_info(background_info)
        state_info = state.get_state_info()


        history.append({"role": "system", "content": f"{role_prompt}{self.description}"})

        # Round 0：制定基础计划。
        task = PROMPT_PLANNER_TASK.format(phase_name=state.phase)
        user_rules = state.generate_rules()


        input = PROMPT_PLANNER.format(
            phases_in_context=state.context,
            phase_name=state.phase,
            state_info=state_info,
            user_rules=user_rules,
            background_info=background_info,
            task=task
        )
        if len(state.memory) > 1:
            previous_plan = state.memory[-2].get("planner", {}).get("plan", "")
            feedback = self._gather_experience_with_suggestion(state)
            input += ("\n# REVISE THE PREVIOUS PLAN #\n" + previous_plan
                      + "\n# REVIEW AND INSIGHT QUALITY FEEDBACK #\n" + feedback
                      + "\nRevise the plan to address every missing tool and field. "
                        "Do not reuse the previous plan unchanged. Require each tool result "
                        "to be printed to stdout for the summarizer; saving results to other files "
                        "does not make them available to it.\n")
        _, history = self.llm.generate(input, history, max_completion_tokens=4096)

        # Round 1 - 提供历史信息和工具
        previous_plan, previous_report = self._get_previous_plan_and_report(state)  # 读取 Understand Background 阶段的输出；该阶段没有内存记录。
        input = f"# PREVIOUS PLAN #\n{previous_plan}\n#############\n# PREVIOUS REPORT #\n{previous_report}\n"
        input += self._read_data(state, num_lines=1)


        tools, tool_names = self._get_tools(state)
        if len(tool_names) > 0:
            input += PROMPT_PLANNER_TOOLS.format(tools=tools, tool_names=tool_names)
        else:
            input += "# AVAILABLE TOOLS #\nThere is no pre-defined Tools in this phase. You can use the functions from public libraries such as Pandas, NumPy, Scikit-learn, etc.\n"

        raw_plan_reply, history = self.llm.generate(input, history, max_completion_tokens=4096)
        with open(f'{state.restore_dir}/raw_plan_reply.txt', 'w', encoding='utf-8') as f:
            f.write(raw_plan_reply)

        # Round 2 - 组织为Markdown格式
        input = PROMPT_PLNNAER_REORGANIZE_IN_MARKDOWN
        organized_markdown_plan, history = self.llm.generate(input, history, max_completion_tokens=4096)
        markdown_plan = self._parse_markdown(organized_markdown_plan)
        with open(f'{state.restore_dir}/markdown_plan.txt', 'w', encoding='utf-8') as f:
            f.write(markdown_plan)

        # Round 3 - 组织为JSON格式
        input = PROMPT_PLNNAER_REORGANIZE_IN_JSON
        raw_json_plan, history = self.llm.generate(input, history, max_completion_tokens=4096)
        with open(f'{state.restore_dir}/raw_json_plan_reply.txt', 'w', encoding='utf-8') as f:
            f.write(raw_json_plan)
        try:
            parsed_plan = self._parse_json(raw_json_plan)
            json_plan = parsed_plan.get('final_answer', parsed_plan)
        finally:
            # Preserve the failed reply and its bounded format repair for diagnosis.
            with open(f'{state.restore_dir}/{self.role}_history.json', 'w', encoding='utf-8') as f:
                json.dump(history, f, ensure_ascii=False, indent=4)
            with open(f'{state.restore_dir}/planner_json_parse.json', 'w', encoding='utf-8') as f:
                json.dump(getattr(self, '_last_json_parse', {}), f, ensure_ascii=False, indent=4)
        with open(f'{state.restore_dir}/json_plan.json', 'w', encoding='utf-8') as f:
            json.dump(json_plan, f, ensure_ascii=False, indent=4)

        # 保存历史
        with open(f'{state.restore_dir}/{self.role}_history.json', 'w', encoding='utf-8') as f:
            json.dump(history, f, ensure_ascii=False, indent=4)

        input_used_in_review = f"   <background_info>\n{background_info}\n    </background_info>"
        print(f"State {state.phase} - Agent {self.role} finishes working.")

        # 用户交互（与原Planner相同）
        with open(SACK_CONFIG_PATH, 'r', encoding='utf-8') as f:
            config = json.load(f)
        user_interaction = config['user_interaction']['plan']
        if user_interaction == "True":
            print("A plan has been generated and saved to 'markdown_plan.txt'.")
            print("You can now review and modify the plan if needed.")
            user_input = builtin_input("Press Enter to continue with the current plan, or type 'edit' to modify: ")
            user_input = user_input.strip().lower()

            if user_input == 'edit':
                print(f"\nPlease edit the file: {state.restore_dir}/markdown_plan.txt")
                print("Save your changes and press Enter when you're done.")
                builtin_input("Press Enter to continue...")
                with open(f'{state.restore_dir}/markdown_plan.txt', 'r', encoding='utf-8') as f:
                    markdown_plan = f.read()

        # 返回结果
        plan = markdown_plan
        result = markdown_plan

        return {
            self.role: {
                "history": history,
                "role": self.role,
                "description": self.description,
                "task": task,
                "input": input_used_in_review,
                "plan": markdown_plan,
                "result": result
            }
        }
