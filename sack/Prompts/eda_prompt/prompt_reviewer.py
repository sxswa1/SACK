EDA_REVIEW_CRITERIA = """
## EDA TOOL-BASED EVALUATION CRITERIA ##

**For PLANNER Assessment:**
- **Tool Coverage Completeness**: Does the plan select ALL necessary predefined EDA tools for comprehensive data exploration?
- **Tool Selection Appropriateness**: Are tools matched to data characteristics (e.g., categorical tools for string columns)?
- **Tool Execution Logic**: Is the tool execution order logical (e.g., data quality 鈫?distribution 鈫?relationships)?
- **Parameter Specification**: Are valid parameters specified for each tool (consistent with tool descriptions)?
- **Redundancy Avoidance**: Are redundant tool calls eliminated (e.g., no repeated missing rate calculation)?

**For DEVELOPER Assessment:**
- **Tool Call Correctness**: Does code call ONLY predefined EDA tools (no custom statistical implementation)?
- **Parameter Accuracy**: Are tools called with correct parameters (matching tool requirements)?
- **Implementation Completeness**: Does code implement ALL planned tool calls?
- **Output Validity**: Are tool outputs structured and machine-readable (for Summarizer processing)?
- **Error Handling**: Are edge cases addressed (e.g., skipping tools for unqualified data)?

**Cross-Agent Consistency:**
- **Plan-Implementation Alignment**: Does code faithfully execute the planned tool calls?
- **Tool-Output Correspondence**: Do tool outputs match the expected results in the plan?
- **Execution Feasibility**: Are tool calls feasible with the available data?
"""

# 修改ROUND0提示词
PROMPT_REVIEWER_ROUND0_EDA = '''
# CONTEXT #
{phases_in_context}
Each phase involves collaboration between multiple agents. You are currently evaluating the performance of agents in Phase: {phase_name}.

#############
# TASK #
Your task is to assess the performance of several agents in completing Phase: {phase_name}, with special focus on:
1. Whether predefined EDA tools are "fully utilized"
2. Correct selection/calling of tools based on their detailed descriptions
3. Alignment between planned tool usage and actual implementation

**EDA Tool-Specific Evaluation Focus:**
1. **Tool Usage Completeness**: Ensure ALL necessary predefined EDA tools are selected/implemented
2. **Tool Call Correctness**: Assess accuracy of tool selection, parameterization, and execution
3. **Implementation Fidelity**: Verify alignment between planned tool calls and actual code
4. **Execution Feasibility**: Evaluate if tool calls are feasible with the available data

You will receive:
- Agent role/description/task/input/result
- FULL context of available predefined EDA tools (list + detailed descriptions)

**Evaluation Requirements:**
- Assign a score from 1 to 5 (1=very poor, 5=excellent) for each agent
- Provide specific suggestions focused on "maximizing tool utilization" (e.g., which key tools were omitted, how to improve parameter configuration)
- Evaluate whether agents have made the most of available tools for the given data characteristics

#############
# RESPONSE: JSON FORMAT #
Let's work this out in a step by step way.

#############
# START EVALUATION #
If you are ready, please request from me the agent information + available EDA tools context.
'''


PROMPT_REVIEWER_ROUND1_EACH_AGENT_EDA = '''
#############
# AGENT {role} TO BE EVALUATED #
<DESCRIPTION>
{description}
</DESCRIPTION>
<TASK>
{task}
</TASK>
<INPUT>
{input}
</INPUT>
<EXECUTION RESULT>
{result}
</EXECUTION RESULT>

#############
# AVAILABLE EDA TOOLS CONTEXT (MANDATORY REFERENCE) #
{tool_context}

#############
# EDA Tool Evaluation Guidance for {role}:#
{eda_evaluation_guidance}

#############
# KEY EVALUATION QUESTIONS (MUST ANSWER) #
1. Did the agent select/call ALL key tools relevant to the data characteristics (tool maximization)?
2. Did the agent use tools in line with their detailed descriptions (parameter/usage correctness)?
3. Were any high-value tools omitted that could have improved EDA comprehensiveness?
4. For Planner: Did the plan reflect full understanding of tool capabilities?
5. For Developer: Did code implement all planned tools with optimal parameterization?
'''

# 为不同agent创建特定的评估指导
AGENT_EDA_EVALUATION_GUIDANCE = {
    "planner": """
    **Core Evaluation Focus: Tool Maximization & Appropriateness**
    1. Tool Coverage: Did the plan include ALL key tools needed for the data type (e.g., cardinality tools for categorical columns)?
    2. Tool Understanding: Did the plan reflect correct understanding of tool capabilities (per detailed descriptions)?
    3. Omitted Tools: Identify any high-value tools that were not included but should have been (e.g., outlier detection for numerical columns with extreme values)
    4. Parameter Logic: Are specified parameters aligned with tool purpose (e.g., reasonable thresholds for missing rate calculation)?
    5. Redundancy vs. Completeness: Ensure no redundant tools, but also no critical omissions.
    """,

    "developer": """
    **Core Evaluation Focus: Tool Utilization & Correctness**
    1. Full Implementation: Did code implement ALL tools from the plan (no omissions)?
    2. Parameter Accuracy: Are tool parameters 100% consistent with their detailed descriptions?
    3. Tool Purity: Did code use ONLY predefined tools (no custom logic replacing tool functionality)?
    4. Maximization: Did code configure tools to their full potential (e.g., using all optional parameters for deeper insight)?
    5. Error Handling: Did code handle edge cases to ensure tools can run (e.g., skipping tools for unqualified data instead of failing)?
    """
}


PROMPT_REVIEWER_ROUND2 = '''
# TASK #
Please extract essential information from your last answer and reorganize into a specified JSON format. You need to organize the information in a clear and concise manner, ensuring that the content is logically structured and easy to understand. You must ensure that the essential information is complete and accurate.

#############
# RESPONSE: JSON FORMAT #
Here is the JSON format you should follow:
```json
{{
    "final_answer": {{
	    "final_suggestion": {{
            str="agent name": str="Specific suggestions for improving the agent's performance"
        }},
        "final_score": {{
            str="agent name": int="The final score you assign to the evaluated agent, only one score in range 1-5"
        }}
    }}
}}
```
Here is an example you can refer to:
```json
{{
    "final_suggestion": {{
        "agent developer": "1. Tool Maximization: Add `analyze_categorical_cardinality` tool call for string columns (omitted in current code). 2. Parameter Optimization: Set `threshold=0.1` for `detect_outliers` (per tool description) instead of default 0.05 to capture meaningful outliers.",
        "agent planner": "1. Tool Coverage: Include `quantify_synergistic_interactions` tool for numerical feature relationships (omitted in plan). 2. Execution Order: Move `calculate_overall_missing_rate` to first step (logical priority per tool usage guidelines)."
    }},
    "final_score": {{
        "agent developer": 3,
        "agent planner": 4
    }}
}}
```

#############
# START REORGANIZING #
'''
