import os
import json
import pdb
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

from typing import List, Dict, Any, Optional
from sack.paths import SACK_CONFIG_PATH, COMPETITION_DATA_DIR, EDA_COMPETITION_DATA_DIR
from sack.utils import load_config
from sack.Prompts.prompt_base import PHASES_IN_CONTEXT_PREFIX
CurrentDir = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = str(SACK_CONFIG_PATH)


class State:
    def __init__(
        self,
        phase: str,
        competition: str,
        message: str = "There is no message.",
        use_mode: Optional[str] = None,
    ):
        self.phase = phase
        self.competition = competition
        self.message = message
        self.memory: List[Dict[str, Any]] = [{}]
        self.current_step = 0
        self.score = 0
        self.finished = False

        self.config = load_config(CONFIG_PATH)
        self.use_mode = use_mode or self.config['use_mode']
        if self.use_mode == 'DSPipeline':
            phase_to_agents = self.config['phase_to_agents']
            self.phase_to_ml_tools = self.config['phase_to_ml_tools']
        else:
            phase_to_agents = self.config['_phase_to_agents']
            self.phase_to_ml_tools = self.config['_phase_to_ml_tools']
        self.agents = phase_to_agents[self.phase]
        self.phase_to_directory = self.config['phase_to_directory']
        self.phase_to_unit_tests = self.config['phase_to_unit_tests']
        self.rulebook_parameters = self.config['rulebook_parameters']



        self.function_to_schema = load_config(f'{CurrentDir}/function_to_schema.json')
        if self.use_mode == 'DSPipeline':
            self.competition_dir = str(COMPETITION_DATA_DIR / self.competition)
        else:
            self.competition_dir = str(EDA_COMPETITION_DATA_DIR / self.competition)
        self.dir_name = self.phase_to_directory[self.phase]
        self.restore_dir = f'{self.competition_dir}/{self.dir_name}'
        self.ml_tools = self.phase_to_ml_tools[self.phase]
        self.background_info = ""
        self.context = ""

    def __str__(self) -> str:
        return f"State: {self.phase}, Current Step: {self.current_step}, Current Agent: {self.agents[self.current_step]}, Finished: {self.finished}"

    def make_context(self) -> None:  # 创建基本背景上下文
        self.context = PHASES_IN_CONTEXT_PREFIX.replace("# {competition_name}", self.competition)  # 装载竞赛名，这里是给某个竞赛创建基本的上下文
        if self.use_mode=='DSPipeline':
            phases = self.config['phases'] # 标识会有多少个阶段
        else:
            phases = self.config['eda_phases']
        self.context += "\n".join(f"{i + 1}. {phase}" for i, phase in enumerate(phases))

    def get_state_info(self) -> str: # 也就是某个阶段的基本上下文信息，描述这阶段要做什么 (不包含理解背景阶段)
        if self.phase == 'Data Preparation':
            return ("In this phase, you have some available files provided by the competition under `rawdata` folder. "
                    "This phase is to prepare all the formatted files required for data science pipeline. "
                    "Carefully analyze the files and data preview that are currently available to you. Your goals are:\n"
                    "1. Locate the training data from the source file and convert it to the required `train.csv`.\n"
                    "2. Locate the test data from the source file and convert it to the required `test.csv`.\n"
                    "3. Generate the sample file of the predicted output `sample_submission.csv`.\n" 
                    "4. Locate the files related to the problem background from the source file and convert it to the required `overview.txt`.\n"
                    "Output: Four standardized files (train.csv, test.csv, sample_submission.csv, overview.txt).")

        elif self.phase == 'Preliminary Exploratory Data Analysis':
            return ("In this phase, you have `train.csv` and `test.csv`. Your goals are:\n"
                    "1. Perform initial data exploration on both datasets.\n"
                    "2. Identify basic statistics, data types, and distributions.\n"
                    "3. Detect potential issues like missing values, outliers, or inconsistencies.\n"
                    "4. Provide insights to guide the subsequent Data Cleaning phase.\n")

        elif self.phase == 'Data Cleaning':
            return ("In this phase, you have `train.csv` and `test.csv`. Your goals are:\n"
                    "1. Address issues identified in the Preliminary EDA phase.\n"
                    "2. Handle missing values using appropriate techniques.\n"
                    "3. Treat outliers and anomalies.\n"
                    "4. Ensure consistency across both datasets.\n"
                    "5. Other necessary data cleaning steps.\n"
                    "6. Create `cleaned_train.csv` and `cleaned_test.csv`.\n"
                    "Output: Cleaned datasets (cleaned_train.csv and cleaned_test.csv).")

        elif self.phase == 'In-depth Exploratory Data Analysis':
            return ("In this phase, you have `cleaned_train.csv` and `cleaned_test.csv`. Your goals are:\n"
                    "1. Conduct thorough statistical analysis on the cleaned data.\n"
                    "2. Explore relationships between features and the target variable.\n"
                    "3. Identify potential feature interactions.\n"
                    "4. Visualize key insights and patterns.\n"
                    "5. Provide recommendations for Feature Engineering.\n")

        elif self.phase == 'Feature Engineering':
            return ("In this phase, you have `cleaned_train.csv` and `cleaned_test.csv`. Your goals are:\n"
                    "1. Create new features based on insights from the In-depth EDA.\n"
                    "2. Transform existing features to improve model performance.\n"
                    "3. Handle categorical variables (e.g., encoding).\n"
                    "4. Normalize or standardize numerical features if necessary.\n"
                    "5. Select the most relevant features for modeling if necessary.\n"
                    "6. Other necessary feature engineering steps.\n"
                    "7. Create `processed_train.csv` and `processed_test.csv`.\n"
                    "Output: Processed datasets (processed_train.csv and processed_test.csv).")

        elif self.phase == 'Model Building, Validation, and Prediction':
            return ("In this phase, you have `processed_train.csv` and `processed_test.csv`. "
                    "You should first train a model on the training set and then make predictions on the test set.\n"
                    "Before training the model:\n"
                    "1. For the training set, separate the target column as y.\n"
                    "2. Remove the target column and any non-numeric columns (e.g., String-type columns) that cannot be used in model training from the training set.\n"
                    "Before making predictions:\n"
                    "1. For the test set, remove the same columns that were removed from the training set (except the target column, which is not present in the test set).\n"
                    "2. Ensure consistency between the columns used in training and prediction.\n"
                    "Due to computational resource limitations, you are allowed to train a maximum of **five** models")

        elif self.phase == "PEDA Insight Extraction":
            return ("In this phase, you have `train.csv` and `test.csv`. Your goals are:\n"
                    "1. Perform comprehensive data quality assessment on both datasets using predefined tools.\n"
                    "2. Identify basic statistics, data types, and distributions with standardized calculation logic.\n"
                    "3. Detect and quantify data issues into quantitative metrics matching the Preliminary EDAInsight fields.\n"
                    "4. Generate all required metrics for Preliminary EDAInsight extraction.\n"
                    "5. Provide insights to guide the subsequent Data Cleaning phase.\n")

        elif self.phase == "IEDA Insight Extraction":
            return ("In this phase, you have `cleaned_train.csv` and `cleaned_test.csv`. Your goals are:\n"
                    "1. Conduct advanced statistical analysis on the cleaned data using predefined tools.\n"
                    "2. Explore complex relationships between features and the target variable with standardized analytical logic.\n"
                    "3. Identify feature interactions and pattern discoveries, quantifying results into metrics matching the In-depth EDAInsight template.\n"
                    "4. Generate strategic quantitative insights for EDAInsight extraction.\n"
                    "5. Provide recommendations for Feature Engineering and Modeling strategies.\n")
        else:
            return ""

    def set_background_info(self, background_info: str) -> None:
        self.background_info = background_info

    def get_current_agent(self) -> str:
        return self.agents[self.current_step % len(self.agents)]

    def generate_rules(self) -> str:  # 添加工具函数应用规则
        if self.rulebook_parameters[self.phase]['status']:  # status 标识是否启用
            user_rules = "\n".join(self.rulebook_parameters[self.phase]['user_defined_rules'])  # 添加user_rules
            default_rules = self.rulebook_parameters[self.phase]['default_rules_with_parameters']
            default_rules = self._format_rules(default_rules)
            rules = user_rules +"\n\n"+ default_rules
        else:
            rules = "There is no rule for this stage."

        with open(f'{self.restore_dir}/user_rules.txt', 'w') as f:
            f.write(rules)
        return rules

    def _format_rules(self, default_rules: Dict[str, List[Any]]) -> str: # 规则格式化并嵌入提示词   values控制各个规则被启用
        formatted_rules = []
        for key, values in default_rules.items():
            if sum(values[0]) == 0: # 不存在某一条规则被启用
                continue
            formatted_rules.append(f"If you need to {key}, please follow the following rules:")
            formatted_rules.extend(
                [f"- {rule[0].format(placeholder=rule[1])}" for i, rule in enumerate(values[1:]) if values[0][i] == 1])  # 某个条目的单一规则被启用
            formatted_rules.append("")
        return "\n".join(formatted_rules)

    def make_dir(self) -> None:
        path_to_dir = f'{self.competition_dir}/{self.dir_name}'
        os.makedirs(path_to_dir, exist_ok=True)
        if 'eda' in self.dir_name:
            os.makedirs(f'{path_to_dir}/images', exist_ok=True)
        self.restore_dir = path_to_dir

    def get_previous_phase(self, type: str = "code") -> Any:
        if self.use_mode=="DSPipeline":
            phases = load_config(CONFIG_PATH)['phases']
        else:
            phases = load_config(CONFIG_PATH)['eda_phases']
        current_phase_index = phases.index(self.phase)

        if current_phase_index == 0:
            return [] if type == 'plan' else None

        if type == 'code':
            if self.phase == 'Data Cleaning' or self.phase == 'PEDA Insight Extraction':
                return 'Understand Background'
            elif self.phase == 'Feature Engineering' or self.phase == 'IEDA Insight Extraction':
                return 'Data Cleaning'
            else:
                return phases[current_phase_index - 1]
        elif type == 'plan':
            if self.phase == "PEDA Insight Extraction":
                return ["Data Preparation", "Understand Background"]
            elif self.phase == "IEDA Insight Extraction":
                return ["Data Preparation", "Understand Background", "Preliminary Exploratory Data Analysis",
                        "Data Cleaning"]
            else:
                return phases[:current_phase_index]
        elif type == 'report':
            if self.phase =="PEDA Insight Extraction":
                return 'Understand Background'
            elif self.phase == "IEDA Insight Extraction":
                return 'Data Cleaning'
            else:
                return phases[current_phase_index - 1]
        else:
            raise ValueError(f"Unknown type: {type}")

    def get_next_phase(self) -> Optional[str]:
        if self.use_mode == "DSPipeline":
            phases = load_config(CONFIG_PATH)['phases']
        else:
            phases = load_config(CONFIG_PATH)['eda_phases']
        current_phase_index = phases.index(self.phase)
        return phases[current_phase_index + 1] if current_phase_index < len(phases) - 1 else None

    def update_memory(self, memory: Dict[str, Any]) -> None:
        print(f"{self.agents[self.current_step]} updates internal memory in Phase: {self.phase}.")
        self.memory[-1].update(memory)

    def restore_memory(self) -> None:
        with open(f'{self.restore_dir}/memory.json', 'w') as f:
            json.dump(self.memory, f, indent=4)
        print(f"Memory in Phase: {self.phase} is restored.")

    def restore_report(self) -> None:
        report = self.memory[-1].get('summarizer', {}).get('report', '')
        if len(report) > 0:
            with open(f'{self.restore_dir}/report.txt', 'w') as f:
                f.write(report)
            print(f"Report in Phase: {self.phase} is restored.")
        else:
            print(f"No report in Phase: {self.phase} to restore.")

    def next_step(self) -> None:
        self.current_step += 1

    def set_score(self) -> None:
        if self.memory[-1].get('summarizer', {}).get('quality_valid') is False:
            self.score = 0
            return
        final_score = self.memory[-1]['reviewer']['score']
        if final_score.get('agent developer', 3) == 0: # developer的分数为0 表示代码没通过 阶段的执行分数就是0
            self.score = 0
        else:
            if len(final_score):
                self.score = sum(float(score) for score in final_score.values()) / len(final_score) # 平均分
            else:
                self.score = 3

    def check_finished(self) -> bool:
        self.finished = self.current_step == len(self.agents)
        return self.finished

