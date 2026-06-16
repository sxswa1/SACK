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
from sack.Prompts.prompt_summarizer import *

class Summarizer(Agent): # 阶段性总结工作 为下一个阶段提供见解
    def __init__(self, model: str, type: str):  
        super().__init__(
            role="summarizer",
            description="You are good at integrating information from available materials.",
            model=model,
            type=type
        )

    def _generate_prompt_round1(self, state: State) -> str:
        prompt_round1 = ""
        current_memory = state.memory[-1]
        for role, memory in current_memory.items():
            trajectory = json.dumps(memory.get("history", []),ensure_ascii=False, indent=4)
            prompt_round1 += f"\n#############\n# TRAJECTORY OF AGENT {role.upper()} #\n{trajectory}"

        return prompt_round1
    
    def _get_insight_from_visualization(self, state: State) -> str: # 对阶段内的可视化输出结果形成见解  要选当前阶段最相关以及下一个阶段最有用的
        from sack.Tools.image_to_text import ImageToTextTool

        images_dir = f"{state.restore_dir}/images"
        if not os.path.exists(images_dir):
            return "There is no image in this phase."
        else:
            images = os.listdir(images_dir)
        count_of_image = 0
        for image in images:
            if image.endswith('png'):
                count_of_image += 1
        if len(images) == 0 or count_of_image == 0:
            return "There is no image in this phase."
        images_str = "\n".join(images)
        num_of_chosen_images = min(5, len(images)) # 最终最多选5张图用于形成见解
        chosen_images = []

        # 挑选本阶段最相关以及下一个阶段最有用的图片 top-max5 of max8
        input = PROMPT_SUMMARIZER_IMAGE_CHOOSE.format(phases_in_context=state.context, phase_name=state.phase, num=num_of_chosen_images+3, images=images_str)
        raw_reply, _ = self.llm.generate(input, [], max_completion_tokens=4096)
        with open(f'{state.restore_dir}/chosen_images_reply.txt', 'w', encoding='utf-8') as f:
            f.write(raw_reply)
        try:
            raw_chosen_images = self._parse_json(raw_reply)['images']
            for image in raw_chosen_images:
                if image in images:
                    chosen_images.append(image)
                    if len(chosen_images) == num_of_chosen_images:
                        break
        except Exception as e:
            logging.error(f"Error parsing JSON: {e}")
            for image in images: # json解析失败  那就直接匹配字符串
                if image in raw_reply:
                    chosen_images.append(image)
                    if len(chosen_images) == num_of_chosen_images:
                        break
        # 图转文模型调用，对这几个可视化图提供文本见解
        image_to_text_tool = ImageToTextTool(model='qwen3-vl-flash', type='api')
        images_to_descriptions = image_to_text_tool.image_to_text(state, chosen_images)
        insight_from_visualization = ""
        for image, description in images_to_descriptions.items():
            insight_from_visualization += f"## IMAGE: {image} ##\n{description}\n"
        with open(f'{state.restore_dir}/insight_from_visualization.txt', 'w', encoding='utf-8') as f:
            f.write(insight_from_visualization)

        return insight_from_visualization

    def _generate_research_report(self, state: State) -> str: # 鍚勪釜闃舵report姹囨€绘垚绔炶禌鐮旂┒鎶ュ憡
        previous_dirs = ['pre_eda', 'data_cleaning', 'deep_eda', 'feature_engineering', 'model_build_predict']
        previous_report = ""
        for dir in previous_dirs:
            if os.path.exists(f'{state.competition_dir}/{dir}/report.txt'):
                with open(f'{state.competition_dir}/{dir}/report.txt', 'r', encoding='utf-8') as f:
                    report = f.read()
                    previous_report += f"## {dir.replace('_', ' ').upper()} ##\n{report}\n"
        # round 0 鎬荤粨鍚勪釜闃舵report 鏄惧紡瑕佹眰涓€浜涙€荤粨瀛楁 鎸夐樁娈垫€荤粨 markdown杈撳嚭  浣嗛渶瑕佸厛璇锋眰鍚勯樁娈祌eport
        _, research_report_history = self.llm.generate(PROMPT_SUMMARIZER_RESEARCH_REPORT, [], max_completion_tokens=4096)
        # round 1 鎷垮埌鎶ュ憡寮€濮嬫€荤粨 鏈€缁坢arkdown杈撳嚭
        raw_research_report, research_report_history = self.llm.generate(previous_report, research_report_history, max_completion_tokens=4096)
        try:
            research_report = self._parse_markdown(raw_research_report)
        except Exception as e:
            research_report = raw_research_report
        return research_report

    def _execute(self, state: State, role_prompt: str) -> Dict[str, Any]:# 以自问自答的方式进行阶段性全面总结，目的是为下一阶段工作提出指导（特别是下一个阶段的planner） 起到阶段过渡作用
        # implement the summarizing function, read the current state's memory and generate report
        if state.memory[-1].get("developer", {}).get("status", True) == False: # 代码有问题的不需要总结，因为下一轮还需要重新代码生成
            print(f"State {state.phase} - Agent {self.role} gives up summarizing because the code execution failed.")
            return {self.role: {"history": [], "report": ""}}

        # 代码通过自然可以正常跳转下一个阶段，这里就要对当前阶段进行总结 为下一阶段的执行提供指导
        history = []
        history.append({"role": "system", "content": f"{role_prompt} {self.description}"})

        # read background_info and plan
        background_info = state.background_info  # 数据集信息
        state_info = state.get_state_info() # 阶段的背景信息 功能 io规定
        if state.phase == "Data Preparation":
            state_info+= PROMPT_DATA_PREPARATION_SUPPLEMENT

        with open(f'{state.restore_dir}/markdown_plan.txt', 'r',encoding='utf-8') as f:
            plan = f.read() # 璇诲彇plan

        # Design questions 通过提出问题 然后回答的方式 对当前阶段的过程进行总结 进而为下一阶段提供指导
        design_questions_history = []
        next_phase_name = state.get_next_phase() # 鑾峰彇涓嬩竴涓樁娈靛悕
        # round 0 提供竞赛的基本上下文背景（包括竞赛名以及涉及的阶段） 当前阶段 以及下一个阶段  要求设计出6个最值得关注且对下一阶段最有帮助的关键问题。  但首先需要请求数据集信息、阶段背景信息、plan（这个阶段做了什么确实用plan最直观）
        input = PROMPT_SUMMARIZER_DESIGN_QUESITONS.format(phases_in_context=state.context, phase_name=state.phase, next_phase_name=next_phase_name)
        _, design_questions_history = self.llm.generate(input, design_questions_history, max_completion_tokens=4096)
        # round 1 提供了这些信息  接下来生成问题
        input = f"# INFO #\n{background_info}\n{state_info}\n#############\n# PLAN #\n{plan}"
        design_questions_reply, design_questions_history = self.llm.generate(input, design_questions_history, max_completion_tokens=4096)
        with open(f'{state.restore_dir}/design_questions_reply.txt', 'w', encoding='utf-8') as f:
            f.write(design_questions_reply)
        # round 2 问题重组成markdown 对于共性问题也要给出一些回答指导（要求）
        input = PROMPT_SUMMARIZER_REORGAINZE_QUESTIONS
        reorganize_questions_reply, design_questions_history = self.llm.generate(input, design_questions_history, max_completion_tokens=4096)

        questions = self._parse_markdown(reorganize_questions_reply)
        with open(f'{state.restore_dir}/questions.txt', 'w', encoding='utf-8') as f:
            f.write(questions)
        history.append(design_questions_history)

        # Answer questions 回答之前提出的问题 会有一些回答的要求（约束）
        with open(f'{state.restore_dir}/single_phase_code.txt', 'r', encoding='utf-8') as f:
            code = f.read() # 读取之前的代码
        with open(f'{state.restore_dir}/{state.dir_name}_output.txt', 'r', encoding='utf-8') as f:
            output = f.read() # 代码执行的输出
            # if len(output) > 1000: # if the output is too long, truncate it
            #     output = output[:1000]
        with open(f'{state.restore_dir}/review.json', 'r', encoding='utf-8') as f:
            review = json.load(f) # reviewer缁欏嚭鐨剆core鍜宻uggestion

        answer_questions_history = []
        # round 0 鎻愪緵绔炶禌鐨勫熀鏈笂涓嬫枃 褰撳墠闃舵 浠ュ強闂  瑕佸杩欎簺闂鍥炵瓟   浣嗛鍏堥渶瑕佽姹傛暟鎹泦淇℃伅銆乸lan銆乧ode銆佷箣鍓嶈緭鍑虹殑涓€浜涘浘鍍忎俊鎭€乺eview
        input = PROMPT_SUMMARIZER_ANSWER_QUESTIONS.format(phases_in_context=state.context, phase_name=state.phase, questions=questions)
        _, answer_questions_history = self.llm.generate(input, answer_questions_history, max_completion_tokens=4096)
        # round 1 填充信息 开始回答问题
        insight_from_visualization = self._get_insight_from_visualization(state) # 从可视化图中获得文字见解
        input = PROMPT_INFORMATION_FOR_ANSWER.format(background_info=background_info, state_info=state_info, plan=plan, code=code, output=output, insight_from_visualization=insight_from_visualization, review=review)
        answer_questions_reply, answer_questions_history = self.llm.generate(input, answer_questions_history, max_completion_tokens=4096)
        with open(f'{state.restore_dir}/answer_questions_reply.txt', 'w', encoding='utf-8') as f:
            f.write(answer_questions_reply)
        # round 2 鎶婇棶棰樺拰鍥炵瓟缁勭粐鎴恗arkdown 浣滀负report
        input = PROMPT_SUMMARIZER_REORGANIZE_ANSWERS
        reorganize_answers_reply, answer_questions_history = self.llm.generate(input, answer_questions_history, max_completion_tokens=4096)

        report = self._parse_markdown(reorganize_answers_reply)
        if state.phase!= "Data Preparation":
            feature_info = self._get_feature_info(state)  # 识别目标变量以及阶段的io数据列（特征） 也就是追踪数据流形态变化  （只用看训练集）
            report = feature_info + report  # 连同report的阶段性问答对作为最终report

        with open(f'{state.restore_dir}/report.txt', 'w', encoding='utf-8') as f:
            f.write(report)
        history.append(answer_questions_history)

        # 最后一个阶段要把所有阶段report都汇总起来 按阶段总结竞赛研究过程 成为一个markdown
        if state.phase == 'Model Building, Validation, and Prediction':
            research_report = self._generate_research_report(state)
            with open(f'{state.competition_dir}/research_report.md', 'w', encoding='utf-8') as f:
                f.write(research_report)

        # save history
        with open(f'{state.restore_dir}/{self.role}_history.json', 'w', encoding='utf-8') as f:
            json.dump(history, f,ensure_ascii=False, indent=4)

        print(f"State {state.phase} - Agent {self.role} finishes working.")
        return {self.role: {"history": history, "report": report}}
