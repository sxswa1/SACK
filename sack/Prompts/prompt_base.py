AGENT_ROLE_TEMPLATE = '''You are an excellent {agent_role}.\n'''

PHASES_IN_CONTEXT_PREFIX = '''
I am working on a data science competition called "# {competition_name}". 
I plan to divide the task into the following phases and complete them in order:
'''

PROMPT_EACH_EXPERIENCE_WITH_SUGGESTION = '''
## EXPERIENCE {index}##
<EXPERIENCE>
{experience}
</EXPERIENCE>
<SUGGESTION>
{suggestion}
</SUGGESTION>
<SCORE>
{score}
</SCORE>
'''

PROMPT_FEATURE_INFO = '''# FEATURE INFO
## TARGET VARIABLE
{target_variable}
## FEATURES BEFORE THIS PHASE
{features_before}
## FEATURES AFTER THIS PHASE
{features_after}
'''

PROMPT_EXTRACT_TOOLS = '''
Please extract the all Tools involved in the following document.
{document}
All available Tools are as follows:
{all_tool_names}

Each tool name MUST be in the available tool names.
Your response should be in the following format:
```json
{{
    "tool_names": [
        "<tool_name 1>",
        "<tool_name 2>",
        "<tool_name 3>",
        ...
    ]
}}
```
'''


PROMPT_REORGANIZE_EXTRACT_TOOLS = '''
# TASK #
Try to reorganize the following information into a JSON format.

# INFORMATION #
{information}

# RESPONSE: JSON FORMAT #
```json
{{
    "tool_names": [
        "<tool_name 1>",
        "<tool_name 2>",
        "<tool_name 3>",
        ...
    ]
}}
```
'''

PROMPT_REORGANIZE_JSON = '''
# TASK #
Please reorganize the following information into a JSON format.
{information}

# RESPONSE: JSON FORMAT #
```json
[json_format]
```
'''


PROMPT_DATA_PREVIEW = '''
# TASK #
Please carefully review the following data and provide a summary of its basic information. Use the specified MARKDOWN format for your summary.
Instructions:
1. Analyze the provided data thoroughly.
2. Summarize the key information.
3. Format your response using the MARKDOWN template below.

Note:
1. The data provided below are partial records of the source file and is ONLY for reference in data preview.

#############
# DATA #
{data}


#############
# RESPONSE: MARKDOWN FORMAT #
```markdown
# Data Information
## Data Type
### ID type
[List features that are unique identifiers for each data point, which will NOT be used in model training.]

### Numerical type
[List features that are numerical values.]

### Categorical type
[List features that are categorical values.]

### Datetime type
[List features that are datetime values.]

## Detailed data description
[Provide a comprehensive description of the data, including any notable patterns, distributions, or characteristics.]

## Target Variable
[Provide the target variable and its description.]

# Submission format (if applicable)
[Provide the format of the submission file, including the required columns and their types.]
```

#############
# START ANALYSIS #
Let's work out this task in a step by step way.
'''


PROMPT_DATA_PREPARATION_SUPPLEMENT='''
#############
# SUPPLEMENTARY INFORMATION #
## ADDITIONAL EXPLANATION ## 
1. `train.csv` is the training set used for model training.
2. `test.csv` is the input data of the test set, and is used for model testing.
3. `sample_submission.csv` is the output sample of the test set, which is used to specify the organization format of the test set output (so the value of the target column can be filled with any value).
4. `overview.txt` is the overview of the current competition.

## REQUIREMENTS ##
Please carefully analyze the following requirements and consider the coupling effects among different processes.
1. Read UTF-8 (including BOM) first; detect another encoding only if decoding fails. Check the entire file, since an ASCII prefix does not imply ASCII-only data.
2. Make sure each data file has ONE header row. Use the documented schema or explicit column names to identify it.
 - Categorical data rows are valid observations, even if most cells are non-numeric. Do not remove them as presumed headers.
 - Merge multiple header rows only when the source schema explicitly defines a multi-row header.
3. First column of all standardized data files must be named `id`:
 - Preserve source identifier values exactly, including strings, leading zeros, gaps and row order. Rename the source ID column to `id`; do not renumber it or require consecutive integers.
 - IDs must be non-empty and unique within each table. The test and sample_submission ID sequences MUST be identical; never require these two tables to have disjoint IDs.
 - Preserve rawdata files, row counts, target values and sample target placeholders. Preparation does not clean, encode or impute data.
4. Ensure that the names of feature columns (as model inputs) are exactly the same in `train.csv` and `test.csv`, and the names of target columns (as model outputs) are exactly the same in `train.csv` and `sample_submission.csv`:
 - Identify the column names in both datasets and check if they are the same.
 - Unify column names if different but obviously corresponding.
 - Raise an ERROR for columns with no correspondence, including error details.
5. `overview.txt` should include a description of the processing procedure during the data preparation phase.
 - Especially the mapping relationship between the source file and the output file.
 - Be careful not to lose any necessary information.

## OUTPUT FILES FORMAT ##
1. `train.csv` contains the id column, the feature columns, and the target columns.
2. `test.csv` contains the id column and the feature columns (no target columns).
3. `sample_submission.csv` contains the id column and the target columns (no feature columns).
4. `overview.txt` contains all the background information and the processing procedure during this phase.

Here is the example of the expected format of the dataset content:
<example>

- train.csv:
id,FeatureName1,FeatureName2,...,TargetName1,TargetName2,...
1,14.325,1.532,...
2,11.368,2.542,...
3,18.378,1.417,...
...

- test.csv:
id,FeatureName1,FeatureName2,...
11,14.325,1.532,...
12,11.368,2.542,...
13,18.378,1.417,...
...

- sample_submission.csv:
id,TargetName1,TargetName2,...
11,1.234,2.234,...
12,1.234,2.234,...
13,1.234,2.234,...
...
</example>
'''
