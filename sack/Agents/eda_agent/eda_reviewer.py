from typing import Dict, Any, List
import json
import logging
import os

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
from sack.Agents.agent_reviewer import Reviewer
from sack.state import State
from sack.Prompts.eda_prompt.prompt_reviewer import *

class EDAReviewer(Reviewer):
    def __init__(self, model: str, type: str):
        super().__init__(
            # role="eda_reviewer",
            # description="You are specialized in assessing data exploration agents' performance for EDAInsight extraction quality.",
            model=model,
            type=type
        )

    def _get_eda_evaluation_guidance(self, role: str) -> str:
        """Initialize the EDA reviewer."""
        role_key = role.lower()
        guidance = AGENT_EDA_EVALUATION_GUIDANCE.get(role_key,"Evaluate general performance and output quality.")
        return guidance

    def _generate_prompt_for_agents(self, state: State) -> List[str]:
        prompt_for_agents = []
        evaluated_agents = list(state.memory[-1].keys())
        print(f"Evaluating agents: {evaluated_agents}")

        tools, tool_names = self._get_tools(state)  # 复用Agent父类的_get_tools方法
        tool_context = f"""
        # AVAILABLE EDA TOOLS IN CURRENT PHASE #
        ## Tool List ##
        {', '.join(tool_names) if tool_names else 'No predefined tools'}

        ## Detailed Tool Descriptions ##
        {tools if tools else 'No tool descriptions available'}
        """


        for each_agent_memory in state.memory[-1].values():
            role = each_agent_memory["role"]
            description = each_agent_memory["description"]
            task = each_agent_memory["task"]
            input = each_agent_memory["input"]
            result = each_agent_memory["result"]

            # 添加EDAInsight特定的评估指导
            eda_guidance = self._get_eda_evaluation_guidance(role)

            prompt_for_agent = PROMPT_REVIEWER_ROUND1_EACH_AGENT_EDA.format(
                role=role.upper(),
                description=description,
                task=task,
                input=input,
                result=result,
                eda_evaluation_guidance=eda_guidance,
                tool_context=tool_context
            )
            prompt_for_agents.append(prompt_for_agent)

        return prompt_for_agents

    def _execute(self, state: State, role_prompt: str) -> Dict[str, Any]:
        # 使用EDA特定的ROUND0提示词
        prompt_for_agents = self._generate_prompt_for_agents(state)
        history = []
        all_raw_reply = []

        # 添加EDA评估标准到系统提示
        enhanced_role_prompt = f"{role_prompt}{self.description}\n\n{EDA_REVIEW_CRITERIA}"
        history.append({"role": "system", "content": enhanced_role_prompt})

        for agent_id in range(len(prompt_for_agents)):
            # 使用EDA特定的ROUND0
            input = PROMPT_REVIEWER_ROUND0_EDA.format(
                phases_in_context=state.context,
                phase_name=state.phase
            )
            raw_reply, history = self.llm.generate(input, history, max_completion_tokens=4096)

            input = prompt_for_agents[agent_id]
            raw_reply, history = self.llm.generate(input, history, max_completion_tokens=4096)

            input = PROMPT_REVIEWER_ROUND2
            raw_reply, history = self.llm.generate(input, history, max_completion_tokens=4096)
            all_raw_reply.append(raw_reply)

        # 其余逻辑保持不变
        all_reply = []
        for each_raw_reply in all_raw_reply:
            reply = self._parse_json(each_raw_reply)
            try:
                all_reply.append(reply['final_answer'])
            except KeyError:
                all_reply.append(reply)

        # 保存历史
        with open(f'{state.restore_dir}/{self.role}_history.json', 'w', encoding='utf-8') as f:
            json.dump(history, f, ensure_ascii=False, indent=4)
        with open(f'{state.restore_dir}/{self.role}_reply.txt', 'w', encoding="utf-8") as f:
            f.write("\n\n\n".join(all_raw_reply))

        review = self._merge_dicts(all_reply, state)
        final_score = review['final_score']
        final_suggestion = review['final_suggestion']

        # 沿用原有的状态检查逻辑。
        if state.memory[-1].get("developer", {}).get("status", True) == False:
            final_score["agent developer"] = 0
            review["final_suggestion"]["agent developer"] = "The code execution failed. Please check the error message and write code again."
        with open(f'{state.restore_dir}/review.json', 'w', encoding='utf-8') as f:
            json.dump(review, f, ensure_ascii=False, indent=4)

        print(f"State {state.phase} - Agent {self.role} finishes working.")
        return {
            self.role: {
                "history": history,
                "score": final_score,
                "suggestion": final_suggestion,
                "result": review
            }
        }
