PROMPT_PLANNER_TASK = '''
Please design plan that ensures COMPLETE data exploration coverage for the current phase: {phase_name}.
The developer will execute tasks based on your plan by calling predefined tools.
I will provide you with INFORMATION, RESOURCE CONSTRAINTS, and previous reports and plans.
You MUST use the following EDA-specific reasoning pattern:
1. Analyze Competition background and data characteristics to identify necessary exploration dimensions, as comprehensive as possible
2. Select appropriate PREDEFINED EDA TOOLS to cover all key exploration dimensions
3. Consider tool dependencies and arrange in logical execution order
4. For each tool, specify CORRECT parameters (use defaults if not specified)
5. Cover every field of the phase EDAInsight template with real predefined tool outputs. For optional temporal/spatial properties, use the predefined tool's applicability detection and its documented no-applicable-data return. Do not invent time or coordinate columns, fabricate statistics, or omit required fields solely because the data is not temporal/spatial.
6. Require every tool result to be printed to stdout, labeled with the exact tool name. The Summarizer does not read separate result files. Use the appropriate classification OR regression tool for the actual target; do not run both unnecessarily.
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
- Scikit-learn
- etc.
## DETAILED TOOL DESCRIPTIONS ##
{tools}
## USAGE RULES ##
1. Predefined tools are tailored for EDAInsight, so tasks prioritize the use of predefined tools for implementation
2. Each tool must be called with valid parameters (refer to tool descriptions)
3. Tool execution order must follow logical dependencies (e.g., calculate missing rate first, then analyze distribution)
'''

PROMPT_PLANNER = '''
# CONTEXT #
{phases_in_context}
Currently, I am at phase: {phase_name}.

#############
# INFORMATION #
{background_info}
{user_rules}
{state_info}

#############
# PLANNING FOCUS: TASK SELECTION & EXECUTION #

## CORE RESPONSIBILITIES ##
1. **Tool Selection**: Choose ONLY from the provided predefined EDA tools to cover key data exploration needs
2. **Dependency Management**: Arrange tools in logical execution sequence
3. **Parameter Specification**: Define valid parameters for each tool (use defaults if no special requirements)
4. **Feasibility Check**: Ensure all tools can be executed with the available data

## PLANNING GUIDELINES ##
1. **Tool-Only Constraint**: The exploration logic must be implemented by predefined tools rather than created by custom ones
2. **Practical Feasibility**: Prioritize tools that match the data characteristics
3. **Template Coverage**: Include tools for every required EDAInsight field, including applicability detection for temporal/spatial properties. If a tool fails, expose the error and correct its inputs; never replace failed results with made-up defaults.
4. **Efficiency**: Avoid redundant tool calls

#############
# TASK #
{task}

#############
# RESPONSE #
Let's work this out in a step by step way to ensure complete EDAInsight coverage.


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

#############
# RESPONSE: MARKDOWN FORMAT #
Here is the MARKDOWN format you should follow:
```markdown
## PLAN
### STEP 1
Task: [The specific task to be performed]
Tools, involved features and correct parameters: [The tools, involved features and correct parameters to be used]
Expected output or Impact on data: [The expected output of the action or the impact of the action on the data]
Constraints: [Any constraints or considerations to keep in mind]

### STEP 2
Task: [The specific task to be performed]
Tools, involved features and correct parameters: [The tools, involved features and correct parameters to be used]
Expected output or Impact on data: [The expected output of the action or the impact of the action on the data]
Constraints: [Any constraints or considerations to keep in mind]

...
```

#############
# CONTENT CONSTRAINTS #
- `Tools` MUST be from the predefined EDA tool list
- The core exploration logic must be implemented by predefined tools rather than created by custom ones

#############
# START REORGANIZING #
'''


PROMPT_PLNNAER_REORGANIZE_IN_JSON = '''
# TASK #
Please extract essential information from your answer and reorganize into the specified JSON format.

#############
# RESPONSE: JSON FORMAT #
Return exactly one valid JSON object, with no prose or type annotations.
Keep the plan concise enough to finish the object within the response limit.
Here is the JSON format you should follow:
```json
{
    "final_answer": [
        {
            "task": "The specific task to be performed",
            "tools, involved features and correct parameters": ["The tools, involved features and correct parameters to be used"],
            "expected output or impact on data": ["The expected output of the action or the impact of the action on the data"],
            "constraints": ["Any constraints or considerations to keep in mind"]
        }
    ]
}
```

#############
# CONTENT CONSTRAINTS #
- `Tools` MUST be from the predefined EDA tool list
- The core exploration logic must be implemented by predefined tools rather than created by custom ones

#############
# START REORGANIZING #
'''
