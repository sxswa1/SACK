PROMPT_PLANNER_TASK = '''
Please design plan that is clear and specific to each FEATURE for the current development phase: {phase_name}. 
The developer will execute tasks based on your plan. 
I will provide you with INFORMATION, RESOURCE CONSTRAINTS, and previous reports and plans.
You can use the following reasoning pattern to design the plan:
1. Break down the task into smaller steps.
2. For each step, ask yourself and answer:
    - "What is the objective of this step?"
    - "What are the essential actions to achieve the objective?"
    - "What features are involved in each action?"
    - "Which tool can be used for each action? What are the parameters of the tool?"
    - "What are the expected output of each action? What is the impact of the action on the data?"
    - "What are the constraints of this step?"
    - "What is the coupling relationship between this step and the other steps?"
    - "Does this step reference any insights from 'RELEVANT INSIGHTS'? If yes:  
        - Which insight? (Specify: Competition[competition_id] -> Pipeline[pipeline_id] -> Insight[insight_id])  
        - How is the insight adapted to the current task? (e.g., adjusted parameters, modified scope)" 
        - Why choose to apply this insight (what significance does it have for the current phase)?
'''

PROMPT_PLANNER_TOOLS = '''
# AVAILABLE TOOLS #
## TOOL LIST ##
You have access to the following predefined tools:
{tool_names}
## ADDITIONAL RESOURCES ##
You can also use functions from public libraries such as:
- Pandas
- NumPy
- Scipy
- Scikit-learn
- etc.
## DETAILED TOOL DESCRIPTIONS ##
{tools}
'''

# 通用：见解引用格式规范（一次定义，多处复用）
INSIGHT_REFERENCE_SPEC = '''
- If referencing insights from "RELEVANT INSIGHTS", use the format:  
  `(Referenced from: Competition[competition_id] -> Pipeline[pipeline_id] -> Insight[Insight_ID]: [adaptation explanation])`  
  Where:  
  - `competition_id` is the unique competition ID (e.g., "playground-series-s3e11")  
  - `pipeline_id` is the unique pipeline ID (e.g., "tetsutani-ps3e11eda-shap")  
  - `Insight_ID` is the original insight ID (e.g., "ci_1")  
  - `[adaptation explanation]` describes how the insight is adjusted for the current task.  
- For multiple insights, separate with semicolons: `(Referenced from: [Insight1]; [Insight2]; ...)`  
- If no insights are referenced, omit this notation.
'''

# 任务的通用核心要素，规划和重组都需包含。
TASK_CORE_ELEMENTS = '''
Each task must include:  
- "Task": Specific action to perform (with insight references if applicable, following the insight_reference_spec).  
- "Tools, involved features and correct parameters": Tools, features, and parameters used.  
- "Expected output or Impact on data": Output description or data impact.  
- "Constraints": Considerations or limitations for the task.
'''

PROMPT_PLANNER = '''
# CONTEXT #
{phases_in_context}
Currently, I am at phase: {phase_name}.

#############
# INFORMATION #
## BACKGROUND ##
{background_info}

## USER RULES ##
{user_rules}

## PHASE CONTEXT ##
{state_info}

## RELEVANT INSIGHTS ##
{relevant_insights}


#############
# NOTE #
## PLANNING GUIDELINES ##
1. Limit the plan to a MAXIMUM of Seven tasks.
2. Provide clear methods and constraints for each task.
3. Focus on critical steps specific to the current phase.
4. Prioritize methods and values mentioned in USER RULES.
5. Offer detailed plans without writing actual code.
6. ONLY focus on tasks relevant to this phase, avoiding those belonging to other phases. 
For example, during the in-depth EDA phase:
    - you CAN perform detailed univariate analysis on KEY features.
    - you CAN NOT modify any feature or modify data.
7. Combine the characteristics of the data science field, infer the processing results of each sub-task involved in the plan and its impact on other sub-tasks, and clearly analyze and define the topological sequence of different sub-tasks. 
Avoid logical problems caused by incorrect subtask orchestration sequences, especially those pointed out in IMPLEMENT CONSTRAINTS.
8. Reference RELEVANT INSIGHTS using standard IDs. {insight_reference_spec}

## DATA OUTPUT PREFERENCES ##
1. Prioritize TEXT format (print) for statistical information.
2. Print a description before outputting statistics.
3. Generate images only if text description is inadequate.

## METHODOLOGY REQUIREMENTS ##
1. Provide highly detailed methods, especially for data cleaning.
2. Specify actions for each feature without omissions.

## RESOURCE MANAGEMENT ##
1. Consider runtime and efficiency, particularly for:
   - Data visualization
   - Large dataset handling
   - Complex algorithms
2. Limit generated images to a MAXIMUM of 10 for EDA.
3. Focus on critical visualizations with valuable insights.

## OPTIMIZATION EXAMPLE ##
When using seaborn or matplotlib for large datasets:
- Turn off unnecessary details (e.g., annot=False in heatmaps)
- Prioritize efficiency in plot generation



#############
# TASK #
{task}

#############
# RESPONSE #
Let's work this out in a step by step way.


#############
# START PLANNING #
Before you begin, please request the following documents from me, which contain important information that will guide your planning:
1. Report and plan from the previous phase
2. Available tools in this phase
3. Sample data for analysis
'''

PROMPT_PLANNER_EXTRACT_SUBTASKS = '''
# TASK #
Please list the task names from your answers and organize them into a specified LIST format.
You must ensure the completeness and accuracy of task names.

#############
# NOTE #
1. Only list the task names without doing any other processing.
2. Only list the task names that are already clearly identified, and DO NOT create new task names.
3. Each task name MUST be a string identified by quotation marks (single quotes or double quotes).

#############
# RESPONSE: LIST FORMAT #
Here is the LIST format you should follow:
[task_name1, task_name2, task_name3,...]

#############
# START #
'''

PROMPT_PLANNER_REORGANIZE_PLAN = '''
# TASK #
Please supplement or revise the detail descriptions of each task in the plan according to the provided rules or constraints.
And add other constraint rules that need to be considered when implementing the plan.

#############
# NOTE #
1. Pay attention to the provided rules or constraints, as they may be of no reference value at the current phase and task.
2. The provided rules or constraints correspond to the planned tasks, please pay attention to matching them accordingly.
3. If the provided rules or constraints conflict with USER RULES, USER RULES shall be given priority.
4. DO NOT change the format of the plan, only the content.
5. Since what you are doing is modifying or adding content, the reorganized plan should include more content (or at least not less).

#############
# PROVIDED RULES OR CONSTRAINS #
{graphrag_constrains}

#############
# START REORGANIZING #
'''

PROMPT_PLNNAER_REORGANIZE_IN_MARKDOWN = '''
# TASK #
Please extract essential information from your answer and reorganize into a specified MARKDOWN format. 
You need to organize the information in a clear and detailed manner, ensuring that the content is logically structured and easy to understand. 
You MUST ensure that the essential information is complete and accurate.

## Key Requirements ##
- Follow {task_core_elements}  
- Strictly adhere to the insight reference format: {insight_reference_spec}

#############
# RESPONSE: MARKDOWN FORMAT #
Here is the MARKDOWN format you should follow:
```markdown
## PLAN
### STEP 1
Task: [Specific task] (Referenced from: Competition[xxx] -> Pipeline[xxx] -> Insight[ci_1]: [adaptation])
Tools, involved features and correct parameters: [The tools, involved features and correct parameters to be used]
Expected output or Impact on data: [The expected output of the action or the impact of the action on the data]
Constraints: [Any constraints or considerations to keep in mind]

### STEP 2
Task: [The specific task to be performed] (No notation needed if no insights are referenced)
Tools, involved features and correct parameters: [The tools, involved features and correct parameters to be used]
Expected output or Impact on data: [The expected output of the action or the impact of the action on the data]
Constraints: [Any constraints or considerations to keep in mind]

...
```

#############
# START REORGANIZING #
'''

PROMPT_PLNNAER_REORGANIZE_IN_JSON = '''
# TASK #
Please extract essential information from your answer and reorganize into a specified JSON format. 
You need to organize the information in a clear and detailed manner, ensuring that the content is logically structured and easy to understand. 
You MUST ensure that the essential information is complete and accurate.

## Key Requirements ##
- Follow {task_core_elements}  
- Strictly adhere to the insight reference format: {insight_reference_spec}

#############
# RESPONSE: JSON FORMAT #
Here is the JSON format you should follow:
```json
{{
    "final_answer": list=[
        {{
            "task": "Specific task (Referenced from: Competition[xxx] -> Pipeline[xxx] -> Insight[ci_1]: [adaptation])",
            "tools, involved features and correct parameters": list=["The tools, involved features and correct parameters to be used"],
            "expected output or impact on data": list=["The expected output of the action or the impact of the action on the data"],
            "constraints": list=["Any constraints or considerations to keep in mind"]
        }}
    ]
}}
```

#############
# START REORGANIZING #
'''

