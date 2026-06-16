PROMPT_QUERY="""
The current development phase is '{phase}'.
What are the domain-specific implementation rules and constraints for the subtask '{task_name}'?

Provide rules and constraints that ensure:
1. Data integrity and quality
2. Appropriate use of tools and parameters
3. Common pitfalls to avoid

Note:
1. The different rules and constraints must to be clearly split.
2. ONLY rules and constraints are returned, nothing else should be included in the final result.
3. Make sure that the final extracted rules and constraints have NO duplicate content. ONLY one of the same contents should be retained.
4. Make sure that the extracted content is the rules and constraints that need to be considered at the current phase.
For example, if the current stage is the 'Data Cleaning', constraints related to 'Model Training' cannot be extracted (even if it is related to the subtask).
5. Limit up to TEN of the most relevant rules or constraints.


Reference format (list):
["retrieved rule1",retrieved rule2,retrieved constraint1,retrieved constraint2,...]

Example:
[
"Compared with the average value, the median is less sensitive to outliers, thus ensuring a more robust representation of the data. Therefore, when filling in the missing values in a numeric column, the median is generally used for filling.",
"When filling in the missing values of the classification column, use pattern values to fill in the missing classification data. This mode represents the most common values in the column, which are reasonable default values for categorical data."
]
"""




PROMPT_INTEGRATE_CONSTRAINTS_JSON="""
# Task Description #
You need to intelligently merge domain-specific constraints retrieved by GraphRAG into the original data science plan based on **exact task name mapping**. The integration should enhance the original constraints with additional domain knowledge while preserving the plan's structure and integrity.

## Integration Rules:
1. **Preserve Original Constraints**: Never delete or modify existing constraints.
2. **Append New Constraints**: Add GraphRAG constraints to the end of the corresponding task's `constraints` list.
3. **Semantic Deduplication**: Filter out constraints that are semantically identical or redundant with existing ones.
4. **Structural Integrity**: Maintain the exact original JSON structure, including field order and formatting.
5. **Categorization**: Group constraints by type (e.g., data quality, tool-specific, best practices) where possible.
6. **Clarity**: Ensure new constraints are concise, actionable, and relevant to the task.

## Example 1 (Simple Merge)
**Original Plan (json_plan)**
```json
[
  {{
    "task": "task_name",
    "tools, involved features and correct parameters": ["tool1(param1)", "tool2(param2)"],
    "expected output or impact on data": ["output1", "output2"],
    "constraints": ["original constraint 1", "original constraint 2"]
  }}
]
```

**GraphRAG Constraints (grag_constraints)**
```json
{{
  "task_name": ["retrieved constraint 1", "retrieved constraint 2"],
  ...
}}
```

**Output Plan**
```json
{{
  "final_answer": [
    {{
      "task": "task_name",
      "tools, involved features and correct parameters": ["tool1(param1)", "tool2(param2)"],
      "expected output or impact on data": ["output1", "output2"],
      "constraints": ["original constraint 1", "original constraint 2", "retrieved constraint 1", "retrieved constraint 2"]
    }},
    ...
  ]
}}
```
# Special Cases Handling #
1. No Matching Task: If a GraphRAG constraint has no corresponding task in the original plan, ignore it.
2. Empty Constraints: If GraphRAG returns empty constraints for a task, keep the original constraints unchanged.
3. Semantic Variations: Merge constraints like "Avoid X" and "Ensure not X" as duplicates.
4. Tool-Specific Constraints: Include constraints that reference tools even if the tool isn't explicitly listed in the original plan.

# Output Requirements #
1. Strict JSON Format: No comments, Markdown, or extraneous text.
2. Field Preservation: Maintain all fields (task, tools, expected outputs) exactly as provided.
3. Ordering: Preserve the original task order and do not sort alphabetically.
4. Validation: Ensure the output is syntactically valid JSON (test with json.loads()).

Original Plan:
{json_plan}
GraphRAG Constraints:
{grag_constraints}
Your Output:
"""

PROMPT_INTEGRATE_CONSTRAINTS_MARKDOWN = """
# Task Description #
You need to intelligently merge domain-specific constraints retrieved by GraphRAG into the original data science plan based on **exact task name mapping**. The integration should enhance the original constraints with additional domain knowledge while preserving the plan's structure and integrity **in Markdown format**.

## Integration Rules:
1. **Preserve Original Constraints**: Never delete or modify existing constraints.
2. **Append New Constraints**: Add GraphRAG constraints to the end of the corresponding task's constraints section in the Markdown file.
3. **Semantic Deduplication**: Filter out constraints that are semantically identical or redundant with existing ones.
4. **Structural Integrity**: Maintain the exact original Markdown structure, including section headings, bullet points, and formatting.
5. **Categorization**: Group constraints by type (e.g., data quality, tool-specific, best practices) where possible.
6. **Clarity**: Ensure new constraints are concise, actionable, and relevant to the task.

## Example 1 (Simple Merge)
**Original Plan (markdown_plan)**
```markdown
### STEP 1
**Task:** Handle Missing Values
**Tools, involved features and correct parameters:**
- **remove_columns_with_missing_data**: `thresh=0.5`
- **fill_missing_values**: 
  - For numerical columns: `method='median'`
  - For categorical columns: `method='mode'`
**Expected output or Impact on data:**
- Cleaned datasets with missing values handled according to the specified rules.
**Constraints:**
- "original constraint 1"
- "original constraint 2"
```

**GraphRAG Constraints (grag_constraints)**
```json
{{
  "task_name": ["retrieved constraint 1", "retrieved constraint 2"],
  ...
}}
```

**Output Plan**
```markdown
### STEP 1
**Task:** Handle Missing Values
**Tools, involved features and correct parameters:**
- **remove_columns_with_missing_data**: `thresh=0.5`
- **fill_missing_values**: 
  - For numerical columns: `method='median'`
  - For categorical columns: `method='mode'`
**Expected output or Impact on data:**
- Cleaned datasets with missing values handled according to the specified rules.
**Constraints:**
- "original constraint 1"
- "original constraint 1"
- "retrieved constraint 1"
- "retrieved constraint 2"
```

# Special Cases Handling #
1. No Matching Task: If a GraphRAG constraint has no corresponding task in the original plan, ignore it.
2. Empty Constraints: If GraphRAG returns empty constraints for a task, keep the original constraints unchanged.
3. Semantic Variations: Merge constraints like "Avoid X" and "Ensure not X" as duplicates.
4. Tool-Specific Constraints: Include constraints that reference tools even if the tool isn't explicitly listed in the original plan.

# Output Requirements #
1. Strict Markdown Format: No comments, JSON, or extraneous text.
2. Field Preservation: Maintain all fields (task, tools, expected outputs) exactly as provided.
3. Ordering: Preserve the original task order and do not sort alphabetically.
4. Validation: Ensure the output is syntactically valid Markdown (test with any Markdown parser).

Original Plan:
{markdown_plan}
GraphRAG Constraints:
{grag_constraints}
Your Output:
"""