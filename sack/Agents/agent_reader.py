from typing import Dict, Any
import json
import re
import logging
import os

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
from sack.Agents.agent_base import Agent
from sack.utils import read_file
from sack.state import State
from sack.Prompts.prompt_base import *
from sack.Prompts.prompt_reader import *



class Reader(Agent):
    def __init__(self, model: str, type: str):
        super().__init__(
            role="reader",
            description="You are good at reading document and summarizing information.",
            model=model,
            type=type
        )
    
    def _execute(self, state: State, role_prompt: str) -> Dict[str, Any]:
        path_to_overview = f'{state.competition_dir}/overview.txt'
        overview = read_file(path_to_overview)
        history = []
        # Understand Background read the overview.txt, generate competition_info.txt
        if len(state.memory) == 1: # if there is no memory before, it means it is the first execution
            history.append({"role": "system", "content": f"{role_prompt}{self.description}"}) # 初始化角色和描述。
            # 模拟多轮对话实现对整个竞赛背景信息的获取与问题理解
            # Round 0：说明 Reader 的职责和当前阶段。
            task = PROMPT_READER_TASK
            input = PROMPT_READER.format(phases_in_context=state.context, task=task)
            raw_reply, history = self.llm.generate(input, history, max_completion_tokens=4096)
            # round 1   problem understand 完成阶段性任务
            input = f"\n#############\n# OVERVIEW #\n{overview}"
            input += self._data_preview(state, num_lines=11)
            raw_reply, history = self.llm.generate(input, history, max_completion_tokens=4096)
            # round 2   output formatting 输出markdown格式化
            reader_mid_reply = raw_reply
            input = PROMPT_READER_ROUND2
            raw_reply, history = self.llm.generate(input, history, max_completion_tokens=4096)

        else: # if there is memory before, concatenate the results of the reader in the previous memory as experience
            self.description = "You are good at reading document and summarizing information." \
                            "You have advanced reasoning abilities and can improve your answers through reflection."# 添加推理和反思的prompt
            experience_with_suggestion = self._gather_experience_with_suggestion(state)
            history.append({"role": "system", "content": f"{role_prompt} {self.description}"})
            # round 0
            task = PROMPT_READER_TASK
            input = PROMPT_READER_WITH_EXPERIENCE_ROUND0.format(phases_in_context=state.context, task=task, experience_with_suggestion=experience_with_suggestion)# 使用包含已有经验的提示词。
            raw_reply, history = self.llm.generate(input, history, max_completion_tokens=4096)
            # round 1
            input = f"# OVERVIEW #\n{overview}\n############# "
            input += self._data_preview(state, num_lines=11)
            raw_reply, history = self.llm.generate(input, history, max_completion_tokens=4096)
            reader_mid_reply = raw_reply
            # round 2
            input = PROMPT_READER_WITH_EXPERIENCE_ROUND2
            raw_reply, history = self.llm.generate(input, history, max_completion_tokens=4096)

        result = raw_reply # 已经格式化了
        reply = self._parse_markdown(raw_reply)# 去掉前后markdown格式标识

        summary = reply

        # save history
        with open(f'{state.restore_dir}/{self.role}_history.json', 'w', encoding='utf-8') as f:  # 保存历史
            json.dump(history, f,ensure_ascii=False, indent=4)
        with open(f'{state.competition_dir}/competition_info.txt', 'w', encoding='utf-8') as f:  # 保存markdown text
            f.write(summary)
        with open(f'{state.restore_dir}/{self.role}_reply.txt', 'w', encoding='utf-8') as f:  # 保存最终格式化的输出。
            f.write(raw_reply)
        with open(f'{state.restore_dir}/{self.role}_mid_reply.txt', 'w', encoding='utf-8') as f:  # 保存中间问题理解的输出
            f.write(reader_mid_reply)
        input_used_in_review = f"   <overview>\n{overview}\n    </overview>"

        print(f"State {state.phase} - Agent {self.role} finishes working.")
        return {
            self.role: {
                "history": history,
                "role": self.role,
                "description": self.description,
                "task": PROMPT_READER_TASK,
                "input": input_used_in_review,
                "summary": summary,
                "result": result
            }
        }

