import os
from typing import Dict, Tuple, List, Optional
import copy
import logging
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

from sack.paths import SACK_CONFIG_PATH
from sack.utils import load_config
from sack.Agents import Reader, Planner, Developer, Reviewer, Summarizer
from sack.Agents.eda_agent import EDAPlanner, EDADeveloper, EDAReviewer, EDASummarizer
from sack.state import State


class SOP:
    def __init__(self, competition: str, use_mode: Optional[str] = None):
        self.competition = competition
        self.use_mode = use_mode
        self.state_records = []
        self.current_state = None
        self.config = self._load_configuration()

    def _load_configuration(self) -> Dict:  # 一些额外的配置
        config = load_config(str(SACK_CONFIG_PATH))
        use_mode = self.use_mode or config['use_mode']
        if use_mode =="DSPipeline":
            phases = config['phases']
        else:
            phases = config['eda_phases']
        return {
            'use_mode': use_mode,
            'max_iterations': 3,  # 每一个阶段最多3轮迭代
            'phases': phases,
            'phase_to_iterations': copy.deepcopy(config['phase_to_iterations'])
        }

    def _create_agent(self, agent_name: str):
        if "Reader" in agent_name:
            agent = Reader("qwen-plus", 'api')
        elif "Planner" in agent_name:
            if agent_name == "EDAPlanner":
                agent = EDAPlanner("qwen-plus", 'api')
            else:
                agent = Planner("qwen-plus", 'api')
        elif "Developer" in agent_name:
            if agent_name == "EDADeveloper":
                agent = EDADeveloper("qwen3-coder-plus", 'api')
            else:
                agent = Developer("qwen3-coder-plus", 'api')
        elif "Reviewer" in agent_name:
            if agent_name == "EDAReviewer":
                agent = EDAReviewer("qwen-plus", 'api')
            else:
                agent = Reviewer("qwen-plus", 'api')
        elif "Summarizer" in agent_name:
            if agent_name == "EDASummarizer":
                agent = EDASummarizer("qwen-plus", 'api')
            else:
                agent = Summarizer("qwen-plus", 'api')
        else:
            return None
        return agent

    def step(self, state: State) -> Tuple[str, State]:  # 阶段内各个agent迁移的步骤step 也就是执行过程
        logging.info(f"Current State: {state}")
        state.make_dir()
        state.make_context()

        while not state.finished:
            current_agent_name = state.get_current_agent()
            current_agent = self._create_agent(current_agent_name)

            if current_agent is None:
                raise ValueError(f"Unknown agent: {current_agent_name}")

            action_result = current_agent.action(state)  # 当前步骤驱动agent执行它的任务
            state.update_memory(action_result)  # 当前阶段的当前步骤的执行记录下来（也就是某个agent的_execute的输出,完整执行记录）
            state.next_step()  # 下一个 agent 接手

            if state.check_finished():  # 当前阶段完成一轮
                state.set_score()  # 阶段的 reviewer 打分更新
                exec_state_info, new_state = self.update_state(state) # 根据当前阶段情况选择切换阶段/下一轮迭代
                if exec_state_info == 'Success':  # 当前阶段完成，切换阶段
                    state.restore_memory()

        return exec_state_info, new_state

    def update_state(self, state: State) -> Tuple[str, Optional[State]]:  # 判断阶段更新
        self.state_records.append(copy.deepcopy(state))

        if state.phase == "Model Building, Validation, and Prediction":
            return self._update_model_building_state(state)
        else:
            return self._update_other_state(state)

    def _update_model_building_state(self, state: State) -> Tuple[str, Optional[State]]:  # 最后模型阶段的阶段迁移判断
        if state.score < 3 and self.config['phase_to_iterations'][state.phase] < self.config[
            'max_iterations']:  # 分数小于预期且未达到最大尝试次数则重复当前阶段
            self.config['phase_to_iterations'][state.phase] += 1
            return "Repeat", self._create_repeat_state(state)
        elif state.score >= 3:
            return "Complete", None  # 最后一个阶段结束了
        else:
            return "Fail", None

    def _update_other_state(self, state: State) -> Tuple[str, Optional[State]]:  # 其他阶段的迁移判断
        if state.phase == "Feature Engineering":
            if len(self.state_records) < 2 or self.state_records[-2].phase != "Model Building, Validation, and Prediction":  # 特征工程怎么会上一个阶段是模型阶段？难道是回溯？
                self.config['phase_to_iterations'][state.phase] += 1
        else:
            self.config['phase_to_iterations'][state.phase] += 1

        if state.score < 3 and self.config['phase_to_iterations'][state.phase] < self.config['max_iterations']:  # 分数小于预期且未达到最大尝试次数则重复当前阶段
            return "Repeat", self._create_repeat_state(state)
        elif state.score >= 3:  # 切换下一个阶段
            if self.config['use_mode'] == "GetEDAInsight" and state.phase == "IEDA Insight Extraction":
                return "Complete", None  # eda鑾峰彇缁撴潫
            else:
                next_phase = self.get_next_phase(state.phase)
                return "Success", State(phase=next_phase, competition=self.competition, use_mode=self.config['use_mode'])
        else:
            return "Fail", None

    def _create_repeat_state(self, state: State) -> State:  # 重复当前阶段，阶段还是这个阶段但state已经是新一轮的state了
        new_state = State(phase=state.phase, competition=self.competition, use_mode=self.config['use_mode'])
        new_state.memory = copy.deepcopy(state.memory)  # memory保留 这个是阶段的memory，可以视为长期记忆内容
        new_state.memory.append({})  # 初始化新阶段的 memory；实际为 [{过往轮该阶段 memory}, {新一轮阶段 memory}]
        return new_state

    def get_next_phase(self, current_phase: str) -> str:  # 切换下一个阶段
        phases = self.config['phases']
        next_index = phases.index(current_phase) + 1
        return phases[next_index] if next_index < len(phases) else "Complete"

