PROMPT_DEVELOPER_TASK_EDA = '''
Develop an efficient solution based on the Planner's provided plan:
1. Implement specific tasks ONLY by calling PREDEFINED EDA tools (NO custom implementation of statistical logic).
2. Ensure each tool is called with CORRECT parameters (refer to tool descriptions).
3. Return structured, machine-readable outputs (consistent with EDAInsight template fields).
4. Keep code minimal: only tool calls + data loading/saving + necessary data preprocessing.
5. Avoid redundant calculations (each EDA tool is called once).

Remember: All statistical analysis (missing rate, outliers, correlation) MUST use predefined EDA tools.
'''


PROMPT_DEVELOPER_EDA = '''
# CONTEXT #
{phases_in_context}
Currently, I am at phase: {phase_name}.

#############
# INFORMATION #
{background_info}
{state_info}

#############
# TASK #
{task}

#############
# PLAN #
{plan}

#############
# RESPONSE: BLOCK (CODE & EXPLANATION) #
TASK 1: [Task Name from Plan]
THOUGHT PROCESS:
[Explain which predefined tool to use and why]
CODE:
```python
[Only predefined tool calls + minimal data handling]
```
EXPLANATION:
[Brief explanation of the tool call and its output]

TASK 2:
[Repeat for each task]
...

#############
# START CODING #
Before you begin, please request the following information from me:
1. Code from previous phases
2. All features of the data
3. Available tools

Once you have this information, provide your complete response with code and explanations for all tasks in a single message.
'''