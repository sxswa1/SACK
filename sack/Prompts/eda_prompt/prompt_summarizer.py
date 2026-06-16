PROMPT_EDAINSIGHT_POPULATION_WITH_TOOLS = '''
# EDAINSIGHT POPULATION WITH EVIDENCE TRACKING (TOOL-BASED) #
Your task is to populate the EDAInsight JSON structure by extracting and integrating results from code execution outputs.

# CORE GUIDANCE #
1. **Fixed Template**: Use the provided fixed EDAInsight template (DO NOT modify the structure)
2. **Tool-Field Alignment**: Populate fields ONLY from the corresponding tool's execution output (see mapping table below)
3. **Multi-Dataset Integration**: First identify Train/Test results for the same field, then merge them by field type (see rules below)
4. **Value Type Compliance**: Ensure values match the template's type requirements (float/bool/list/dict)
5. **Evidence Tracking**: Link every populated value to the exact tool that generated it

# MULTI-DATASET RESULT INTEGRATION RULES (CRITICAL) #
For fields with both Train and Test results, apply these integration strategies in order:
## 1. Numerical Fields (float/int)
- Calculate the **arithmetic mean** of Train and Test values (e.g., Train=0.0293, Test=0.0302 → value=0.02975)
- If values differ significantly (>10% relative difference), add a note in `_evidence` about the discrepancy
## 2. Categorical/Enumerated Fields (str like pattern_type)
- If Train and Test values are identical: use the value directly
- If different: use the majority value (or Train value if no majority) and note the conflict in `_evidence`
## 3. Dictionary Fields (e.g., column_missing_distribution)
- For numerical values inside dict: calculate mean of Train/Test corresponding values
- For categorical values inside dict: follow rule 2
- Preserve the original dict structure
## 4. List Fields (e.g., bins/proportions)
- For string lists (bins): use Train list (must match Test list structure)
- For numerical lists (proportions): calculate element-wise mean of Train/Test lists
## 5. Boolean Fields
- If Train and Test values are identical: use the value directly
- If different: mark as True (conflict) and note in `_evidence`
## 6. Special Case: No Test Data
- Use Train value directly (note "only train data available" in `_evidence`)


# CURRENT PHASE TOOLS & MAPPED FIELDS #
{tool_mapping_table}

# FIXED EDAINSIGHT TEMPLATE (PRESERVE STRUCTURE) #
{eda_insight_template}

# CURRENT PHASE PREDEFINED TOOLS #
The following tools were executed in this phase and their outputs must be extracted:
{current_phase_tools}

# TOOL CONTEXT (REFERENCE) #
Detailed descriptions of the predefined tools:
{tool_context}

# VALUE TYPE RULES (CRITICAL) #
- float: Use numerical values (e.g., 0.25, 10.0) - NO strings like "25%"
- bool: Use True/False (not "Yes"/"No" or 1/0)
- List[str/float]: Use valid JSON lists (e.g., ["0-10%", "10-20%"], [0.1, 0.2])
- Dict: Keep nested structure matching the template
- Unknown: Leave as "unknown" if no tool output is available (no evidence wrapper)

# REQUIRED EVIDENCE STRUCTURE #
For EACH non-"unknown" field, use this structure:
```json
"field_name": {{
  "value": <actual_value_matching_type_requirements>,
  "_evidence": {{
    "source": "code_output",
    "tool": "<name_of_tool_that_provided_this_value>",
    "extract": "exact text/data from tool output",
    "confidence": "high|medium|low",
    "integration_note":"<note about integration (e.g., mean of train/test, conflict resolution)>"
  }}
}}

# AVAILABLE INFORMATION SOURCES #
## ANALYSIS PLAN (Tool Selection/Execution Order) ##
Which tools were planned to be executed:
{plan}

## CODE EXECUTION OUTPUT (Primary Source) ##  
Raw results from generated code with predefined EDA tools:
{code_output}

## QUALITY ASSESSMENT (Tool Execution Review) ##
Reviewer evaluation of tool execution quality:
{review}

## VISUAL PATTERN INSIGHTS (Supplemental) ##
Insights from tool-generated visualizations:
{visual_insights}

# FINAL RULES #
1.Preserve the EXACT structure of the fixed template (no added/removed fields)
2.Populate values ONLY from tool execution outputs (no invented values)
3.Strictly follow Train/Test integration rules for all fields
4.Include evidence tracking for all non-"unknown" fields
5.Ensure all values match the template's type requirements

Return ONLY the populated EDAInsight JSON object (including evidence tracking).
'''