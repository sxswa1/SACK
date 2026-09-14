from typing import Dict, Any, List
import json
import re
import logging
import os
import pdb

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
from sack.Agents.agent_base import Agent
from sack.utils import read_file
from sack.state import State
from sack.Prompts.prompt_base import *
from sack.Prompts.prompt_reviewer import *

class Reviewer(Agent):
    def __init__(self, model: str, type: str):  
        super().__init__(
            role="reviewer",
            description="You are skilled at assessing the performance of one or more agents in completing a given task. Provide detailed scores for their performance and offer constructive suggestions to optimize their results.",
            model=model,
            type=type
        )

    def _merge_dicts(self, dicts: List[Dict[str, Any]], state: State) -> Dict[str, Any]:
        merged_dict = {"final_suggestion": {}, "final_score": {}}

        # define the keys to be unified
        if state.phase == 'Understand Background': # 背景理解的前驱agent只有reader
            key_mapping = {
                "reader": "agent reader"
            }
        else: # 其他情况的前驱是planner和developer
            key_mapping = {
                "planner": "agent planner",
                "developer": "agent developer"
            }
        
        try:
            for d in dicts: # 对每个agent的json text （包含final_score和final_suggestion两个字段）  把不同agent的score、suggestion分别整合到一块  也就是一个dict的score、suggestion字段包含所有agent的score、suggestion
                if not isinstance(d, dict):
                    continue
                suggestions = d.get("final_suggestion") or d.get("suggestion") or {}
                scores = d.get("final_score") or d.get("score") or {}
                if not isinstance(suggestions, dict):
                    suggestions = {}
                if not isinstance(scores, dict):
                    scores = {}
                for key in suggestions: # 找到当前agent的suggestion
                    normalized_key = key.lower()
                    for k, v in key_mapping.items():
                        if k in normalized_key:
                            normalized_key = v  # 当前agent匹配到目标命名
                            break
                    merged_dict["final_suggestion"][normalized_key] = suggestions[key]
                for key in scores:
                    normalized_key = key.lower()
                    for k, v in key_mapping.items():
                        if k in normalized_key:
                            normalized_key = v
                            break
                    merged_dict["final_score"][normalized_key] = scores[key]
        except Exception as e:
            logging.error(f"Error: {e}")
            # pdb.set_trace()

        expected_agents = list(key_mapping.values())
        for agent_name in expected_agents:
            merged_dict["final_score"].setdefault(agent_name, 0)
            merged_dict["final_suggestion"].setdefault(
                agent_name,
                "Reviewer output could not be parsed into the expected schema. Please regenerate this stage."
            )
        
        return merged_dict # 合并所有 Agent 信息后的字典。

    def _generate_prompt_for_agents(self, state: State) -> List[str]:
        prompt_for_agents = []
        evaluated_agents = list(state.memory[-1].keys()) # get all agents in the previous state （应该是current state）
        print(f"Evaluating agents: {evaluated_agents}")
        for each_agent_memory in state.memory[-1].values(): # get the current state's memory
            role = each_agent_memory["role"]
            description = each_agent_memory["description"]
            task = each_agent_memory["task"]
            input = each_agent_memory["input"]
            result = each_agent_memory["result"]
            # 评估某个角色 要结合它的角色定义 任务 输入和输出 进行全面评估
            prompt_for_agent = PROMPT_REVIEWER_ROUND1_EACH_AGENT.format(role=role.upper(), description=description, task=task, input=input, result=result)
            prompt_for_agents.append(prompt_for_agent)
        return prompt_for_agents
    
    def _execute(self, state: State, role_prompt: str) -> Dict[str, Any]:# 为当前阶段前驱所有agent评价和建议
        # implement the evaluation function
        # the second round input: the role_description, task, input, result of each agent in the previous state
        prompt_for_agents = self._generate_prompt_for_agents(state)  # 对当前阶段，之前的任何agent的评估 所需的语料
        history = []
        all_raw_reply = []
        history.append({"role": "system", "content": f"{role_prompt}{self.description}"})

        for agent_id in range(len(prompt_for_agents)): # 对每个agent 提取score和suggestion （一次只对一个agent评估）
            # round=0 reviewer的任务定义 需先请求该阶段先前其他agent的语料
            input = PROMPT_REVIEWER_ROUND0.format(phases_in_context=state.context, phase_name=state.phase)
            raw_reply, history = self.llm.generate(input, history, max_completion_tokens=4096)
            # round=1 注入某个agent评估所需的语料（这个agent的定义职能以及io） 可以开始评估 评估分数1~5 并给出建议
            input = prompt_for_agents[agent_id]
            raw_reply, history = self.llm.generate(input, history, max_completion_tokens=4096)
            # round=2 返回结果提取成json
            input = PROMPT_REVIEWER_ROUND2
            raw_reply, history = self.llm.generate(input, history, max_completion_tokens=4096)
            all_raw_reply.append(raw_reply)


        all_reply = []
        # pdb.set_trace()
        for each_raw_reply in all_raw_reply:
            reply = self._parse_json(each_raw_reply)
            try:
                all_reply.append(reply['final_answer']) # json text
            except KeyError:
                # pdb.set_trace()
                all_reply.append(reply)

        # save history
        with open(f'{state.restore_dir}/{self.role}_history.json', 'w', encoding='utf-8') as f:
            json.dump(history, f,ensure_ascii=False, indent=4)
        with open(f'{state.restore_dir}/{self.role}_reply.txt', 'w',encoding="utf-8") as f:
            f.write("\n\n\n".join(all_raw_reply))

        review = self._merge_dicts(all_reply, state)  # 多个agent的suggestion、score合并
        final_score = review['final_score']
        final_suggestion = review['final_suggestion']
        # developer code execution failed, score is 0      human-in-the-loop 强制修改分数和建议
        if state.memory[-1].get("developer", {}).get("status", True) == False: # developer的代码如果没有通过（无论是有bug还是没过unit test）
            final_score["agent developer"] = 0 # 强制把代码没通过的developer分数置0（final_score直接改0，但final_suggestion其实并命由强制更改）
            review["final_suggestion"]["agent developer"] = "The code execution failed. Please check the error message and write code again." # 建议也强制改成重写代码
        with open(f'{state.restore_dir}/review.json', 'w', encoding='utf-8') as f:
            json.dump(review, f,ensure_ascii=False, indent=4)

        print(f"State {state.phase} - Agent {self.role} finishes working.")
        return {
            self.role: {
                "history": history, 
                "score": final_score, 
                "suggestion": final_suggestion, 
                "result": review
            }
        }

