from typing import Dict,List, Any
import json
import re
import logging
import os
import ast
from builtins import input as builtin_input

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

from sack.Agents.agent_base import Agent
from sack.Agents.agent_grag import GraphRetriever
from sack.utils import read_file
from sack.state import State
from sack.paths import SACK_CONFIG_PATH
from sack.Prompts.prompt_base import *
from sack.Prompts.prompt_planner import *

class Planner(Agent):
    def __init__(self, model: str, type: str):  
        super().__init__(
            role="planner",
            description="You are good at planning tasks and creating roadmaps.",
            model=model,
            type=type
        )

    def _get_previous_plan_and_report(self, state: State): # 过往阶段的report（总结性信息）和plan历史memory
        previous_plan = ""
        previous_dir_name = None
        previous_phases = state.get_previous_phase(type="plan") # 返回过去的所有阶段
        for previous_phase in previous_phases: # 閬嶅巻鑾峰彇杩囧幓鍚勪釜闃舵鐨剅eport鍜宲lan锛堥暱鏈熻蹇嗭級
            previous_dir_name = state.phase_to_directory[previous_phase] # 姣忎釜闃舵鐨勫巻鍙茶蹇嗭紙瀛樺偍鍦ㄦ湰鍦扮殑闀挎湡璁板繂锛夐兘鍦ㄥ搴旂殑鏂囦欢澶逛笅淇濆瓨
            previous_plan += f"## {previous_phase.upper()} ##\n"
            path_to_previous_plan = f'{state.competition_dir}/{previous_dir_name}/plan.json'
            if os.path.exists(path_to_previous_plan):
                with open(path_to_previous_plan, 'r',encoding='utf-8') as f:
                    previous_plan += f.read()
                    previous_plan += '\n'
            else:
                previous_plan = "There is no plan in this phase.\n"
        path_to_previous_report = f'{state.competition_dir}/{previous_dir_name}/report.txt'
        if os.path.exists(path_to_previous_report):
            previous_report = read_file(path_to_previous_report)
        else:
            previous_report = "There is no report in the previous phase.\n"
        return previous_plan, previous_report



    def _parse_subtask_from_plan(self, subtasks_str: str) -> List[str]:
        if not subtasks_str or not subtasks_str.strip():
            return []

        # 匹配最外层方括号内容（允许跨行）
        matches = re.findall(r'\[([^\]]*)\]', subtasks_str, re.DOTALL)
        if not matches:
            return []

        list_content = matches[-1].strip()
        if not list_content:  # 空列表 []
            return []

        # 匹配最外层方括号内容（允许跨行）
        quoted_items = []
        # 鍖归厤鍗曞紩鍙锋垨鍙屽紩鍙峰寘鍥寸殑瀛楃涓诧紙鏀寔杞箟鍜岃法琛岋級
        quote_pattern = r'([\'"])(?:(?!\1).|\\.)*?\1'
        for match in re.finditer(quote_pattern, list_content, re.DOTALL):
            quoted_str = match.group(0)
            try:
                # 浣跨敤AST瀹夊叏瑙ｆ瀽瀛楃涓诧紙澶勭悊鎵€鏈夎浆涔夊瓧绗︼級
                parsed = ast.literal_eval(quoted_str)
                quoted_items.append(str(parsed))
            except (ValueError, SyntaxError):
                # 瑙ｆ瀽澶辫触鏃朵娇鐢ㄥ師濮嬪瓧绗︿覆锛堝幓闄ゅ鍥村紩鍙凤級
                quoted_items.append(quoted_str[1:-1])

        if quoted_items:
            return quoted_items

        # 方案2：回退到CSV解析（如果方案1无匹配）
        try:
            import csv
            from io import StringIO
            reader = csv.reader(StringIO(list_content), skipinitialspace=True)
            return [item for row in reader for item in row if item]
        except ImportError:
            # 鏃燙SV妯″潡鏃朵娇鐢ㄧ畝鍗曞垎鍓诧紙鏈€鍚庢墜娈碉級
            return [s.strip() for s in list_content.split(',') if s.strip()]



    def _execute(self, state: State, role_prompt: str) -> Dict[str, Any]:
        history = []
        if state.phase != "Data Preparation":
            num_lines=11
        else:
            num_lines=6
        data_preview = self._data_preview(state, num_lines=num_lines)  # 瀵规暟鎹泦鍒嗘瀽
        background_info = f"Data preview:\n{data_preview}"
        state.set_background_info(background_info) # 数据集信息加载
        state_info = state.get_state_info() # 闃舵鑳屾櫙淇℃伅
        if state.phase == "Data Preparation":
            state_info+= PROMPT_DATA_PREPARATION_SUPPLEMENT


        if len(state.memory) == 1: # if there is no memory before, it means it is the first execution 该阶段的第一轮

            history.append({"role": "system", "content": f"{role_prompt}{self.description}"})

            # Round 0   竞赛上下文信息、阶段信息、阶段的预定义规则、数据集信息、阶段性任务   这些信息全部作为planner的基本prompt(职能定义)
            # 但是还有一些需要的信息 如之前阶段的report和plan  作为memory也需要作为上下文信息考虑进去  因此需要请求
            # eda_phase_support = ""
            # if state.phase in ["Preliminary Exploratory Data Analysis","In-depth Exploratory Data Analysis"]:  # 鍘绘帀瀹忚EDA
            #     eda_phase_support = PROMPT_EDA_PHASE_SUPPORT
            task = PROMPT_PLANNER_TASK.format(phase_name=state.phase)  # planner鐨勮闃舵浠诲姟

            user_rules = state.generate_rules() # 浜哄畾涔夌殑鍚勪釜闃舵涓叿浣撲换鍔℃墽琛岀殑涓€浜涜鍒欙紝渚嬪浠€涔堟儏鍐典笅鎶婄己澶卞€煎垪鏁村垪鍓旈櫎锛岃鍒掓椂瑕佽€冭檻杩涘幓

            if state.use_mode == "DSPipeline" and state.phase !="Data Preparation":
                # if state.phase in ["Preliminary Exploratory Data Analysis","In-depth Exploratory Data Analysis"]:  # 去掉宏观EDA
                sack_case_retriever = self.get_sack_case_retriever()
                if sack_case_retriever is None:
                    relevant_insights = "There are no relevant insights."
                else:
                    phase_filtered_insights = sack_case_retriever.get_similar_comp_coreinsight(state, retrieval_mode = "recall_rerank")
                    relevant_insights = sack_case_retriever.get_phase_insights_text(
                        filtered_insights=phase_filtered_insights
                    )
            else:
                relevant_insights = "There are no relevant insights."

            # input = PROMPT_PLANNER.format(phases_in_context=state.context, phase_name=state.phase, state_info=state_info,user_rules=user_rules,
            #                               background_info=background_info, relevant_insights=relevant_insights,task=task,insight_reference_spec=INSIGHT_REFERENCE_SPEC,eda_phase_support=eda_phase_support)
            input = PROMPT_PLANNER.format(phases_in_context=state.context, phase_name=state.phase, state_info=state_info,user_rules=user_rules,
                                          background_info=background_info, relevant_insights=relevant_insights,task=task,insight_reference_spec=INSIGHT_REFERENCE_SPEC)
            _, history = self.llm.generate(input, history, max_completion_tokens=4096)

            # Round 1 将过往阶段的report和plan的长期记忆都给planner  当前阶段可用工具也提供
            input = f"# PREVIOUS PLAN #\n{self._get_previous_plan_and_report(state)[0]}\n#############\n# PREVIOUS REPORT #\n{self._get_previous_plan_and_report(state)[1]}\n"
            if state.phase!="Data Preparation":
                input += self._read_data(state, num_lines=1) # 鏁版嵁闆嗙殑绗竴琛屼綔涓烘牱渚嬪嵆鍙紙杩欓噷鎸嘾ataset鎴杅eature set 瀵瑰簲鏁版嵁澶勭悊鎴栫壒寰佸伐绋嬮樁娈碉級
            else :
                input += self._read_data(state, num_lines=5)
            tools, tool_names = self._get_tools(state)   # 获取当前阶段的所有工具
            if len(tool_names) > 0:
                input += PROMPT_PLANNER_TOOLS.format(tools=tools, tool_names=tool_names)  # 预定义工具+公开库工具
            else:# 娌℃湁棰勫畾涔夌殑宸ュ叿灏卞彧鐢ㄥ叕寮€搴撶殑宸ュ叿
                input += "# AVAILABLE TOOLS #\nThere is no pre-defined Tools in this phase. You can use the functions from public libraries such as Pandas, NumPy, Scipy, Scikit-learn, etc.\n"
            raw_plan_reply, history = self.llm.generate(input, history, max_completion_tokens=4096)  # 开始规划任务
            with open(f'{state.restore_dir}/raw_plan_reply.txt', 'w',encoding='utf-8') as f: # 阶段的规划信息入库
                f.write(raw_plan_reply)

            # Round 2  把plan组织成markdown格式  其实返回的就是 任务、工具-涉及的特征-参数、预期输出/数据形态变化、约束条件 *n
            input = PROMPT_PLNNAER_REORGANIZE_IN_MARKDOWN.format(task_core_elements=INSIGHT_REFERENCE_SPEC,insight_reference_spec=TASK_CORE_ELEMENTS)
            organized_markdown_plan, history = self.llm.generate(input, history, max_completion_tokens=4096)
            markdown_plan = self._parse_markdown(organized_markdown_plan)
            with open(f'{state.restore_dir}/markdown_plan.txt', 'w',encoding='utf-8') as f:
                f.write(markdown_plan)

            # Round 3  plan涔熻缁勭粐鎴恓son鏍煎紡 瀛樻。
            input = PROMPT_PLNNAER_REORGANIZE_IN_JSON.format(task_core_elements=INSIGHT_REFERENCE_SPEC,insight_reference_spec=TASK_CORE_ELEMENTS)
            raw_json_plan, history = self.llm.generate(input, history, max_completion_tokens=4096)
            try:
                json_plan = self._parse_json(raw_json_plan)['final_answer']
            except Exception as e:
                logger.info(f"Error parsing JSON: {e}")
                json_plan = self._parse_json(raw_json_plan)
            with open(f'{state.restore_dir}/json_plan.json', 'w',encoding='utf-8') as f:
                json.dump(json_plan, f, ensure_ascii=False,indent=4)

            # # 自定义 Round 4 plan通过graphrag 增加约束
            # retriever=GraphRetriever(model="qwen2.5-14b-instruct",type='api',knowledge_graph_path="D:/PythonProject/graphrag")
            # enriched_json_plan,enriched_markdown_plan= retriever._execute(state)


        else:  # 在进行该阶段的新一轮时，如果上一轮结束的分数不可接受，则沿用上一轮的plan（永远不修改plan？） 自然也无需后续的记忆入库操作
            last_planner_score = state.memory[-2].get("reviewer", {}).get("score", {}).get("agent planner", 0) # 上一轮planner的得分
            if last_planner_score >= 3: # if the score of the last planner is greater than or equal to 3, it means the planner's plan is acceptable
                return {"planner": state.memory[-2]["planner"]}
            else: # 杩欓噷鏈変簺鐤戦棶 涓轰綍planner鐨勮鍒掍笉鍙帴鍙楄繕瑕佹部鐢╬lanner鐨勭粨鏋滆€屼笉鏄噸鏂拌鍒掞紵
                return {"planner": state.memory[-2]["planner"]}

        # save history  planner鍙湁绗竴杞繚瀛榩lan
        with open(f'{state.restore_dir}/{self.role}_history.json', 'w',encoding='utf-8') as f:
            json.dump(history, f, ensure_ascii=False,indent=4)


        # reviewer鍦ㄨ瘎浠锋椂鍙渶瑕佹牴鎹緭鍏ユ暟鎹泦鐨勪俊鎭嵆鍙缁撴灉璇勪环
        input_used_in_review = f"   <background_info>\n{background_info}\n    </background_info>"

        print(f"State {state.phase} - Agent {self.role} finishes working.")

        # 鍏佽鐢ㄦ埛淇敼plan
        with open(SACK_CONFIG_PATH, 'r',encoding='utf-8') as f:
            config = json.load(f)
        user_interaction = config['user_interaction']['plan'] # 用户是否参与交互（是否启用human in the loop）
        if user_interaction == "True":
            # user interaction here
            print("A plan has been generated and saved to 'markdown_plan.txt'.")
            print("You can now review and modify the plan if needed.")
            print("If you want to get some suggestions for modifying the plan, please type 'suggestion'.")
            user_input = builtin_input("Press Enter to continue with the current plan, or type 'edit' to modify: ")
            user_input = user_input.strip().lower()

            if user_input == 'edit':
                print(f"\nPlease edit the file: {state.restore_dir}/markdown_plan.txt") # 鍏佽浜虹洿鎺ヤ慨鏀筽lan
                print("Save your changes and press Enter when you're done.")
                builtin_input("Press Enter to continue...")
                # Re-read the potentially modified plan
                with open(f'{state.restore_dir}/markdown_plan.txt', 'r',encoding='utf-8') as f:
                    markdown_plan = f.read()
            elif user_input == 'suggest':
                print(f"\nPlease refer to note section for each function in the file `ml_tools_doc/{state.restore_dir}_tools.md`.")
            elif user_input:
                print("Invalid input. Continuing with the current plan.")
            else:
                print("Continuing with the current plan.")

        # save plan and result
        plan = markdown_plan # 鍙兘鏄凡缁忎汉涓轰慨鏀瑰悗鐨刾lan
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
