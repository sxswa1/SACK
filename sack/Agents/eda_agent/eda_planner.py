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


        if len(state.memory) == 1:  # 第一阶段执行
            history.append({"role": "system", "content": f"{role_prompt}{self.description}"})

            # Round 0 - 鍩虹瑙勫垝
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
            _, history = self.llm.generate(input, history, max_completion_tokens=4096)

            # Round 1 - 提供历史信息和工具
            previous_plan, previous_report = self._get_previous_plan_and_report(state)  # 杩欓噷鑾峰彇鐨勬槸background understand闃舵 鍥犳娌℃湁鍐呭
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

            # Round 2 - 缁勭粐涓篗arkdown鏍煎紡
            input = PROMPT_PLNNAER_REORGANIZE_IN_MARKDOWN
            organized_markdown_plan, history = self.llm.generate(input, history, max_completion_tokens=4096)
            markdown_plan = self._parse_markdown(organized_markdown_plan)
            with open(f'{state.restore_dir}/markdown_plan.txt', 'w', encoding='utf-8') as f:
                f.write(markdown_plan)

            # Round 3 - 缁勭粐涓篔SON鏍煎紡
            input = PROMPT_PLNNAER_REORGANIZE_IN_JSON
            raw_json_plan, history = self.llm.generate(input, history, max_completion_tokens=4096)
            try:
                json_plan = self._parse_json(raw_json_plan)['final_answer']
            except Exception as e:
                logger.info(f"Error parsing JSON: {e}")
                json_plan = self._parse_json(raw_json_plan)
            with open(f'{state.restore_dir}/json_plan.json', 'w', encoding='utf-8') as f:
                json.dump(json_plan, f, ensure_ascii=False, indent=4)

        else:  # 鍚庣画杞
            last_planner_score = state.memory[-2].get("reviewer", {}).get("score", {}).get("agent planner", 0)
            if last_planner_score >= 3:
                return {"planner": state.memory[-2]["planner"]}
            else:
                return {"planner": state.memory[-2]["planner"]}

        # 淇濆瓨鍘嗗彶
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

        # 杩斿洖缁撴灉
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
