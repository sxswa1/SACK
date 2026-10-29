PROMPT_REVIEWER_ROUND0 = '''
# CONTEXT #
{phases_in_context}
Each phase involves collaboration between multiple agents. You are currently evaluating the performance of agents in Phase: {phase_name}.

#############
# TASK #
Your task is to assess the performance of several agents in completing Phase: {phase_name}.
I will provide descriptions of each agent, the tasks they performed, and the outcomes of those tasks.
Please assign a score from 0 to 5 for each agent, with 0 indicating a critical failure, 1 indicating very poor performance and 5 indicating excellent performance.
Additionally, provide specific suggestions for improving each agent's performance, if applicable.
If an agent's performance is satisfactory, no suggestions are necessary.

#############
# RESPONSE: JSON FORMAT #
Let's work this out in a step by step way.

#############
# START EVALUATION #
If you are ready, please request from me the role, description, input, task and execution result of the agent to be evaluated.
'''

PROMPT_REVIEWER_ROUND1_EACH_AGENT = '''
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

'''

PROMPT_REVIEWER_ROUND2 = '''Return exactly one valid JSON object for the ONE agent just evaluated.
Use that agent's name in all fields. Preserve the evaluation, including all critical failures.
Required format (example for developer; substitute reader/planner when evaluating them):
```json
{
  "final_score": {"agent developer": 0},
  "final_suggestion": {"agent developer": "Run actual training and report measured validation results."},
  "critical_failures": [
    {"agent": "agent developer", "code": "FABRICATED_METRIC", "evidence": "The code assigns accuracy=0.95 without calculating it."}
  ]
}
```
Use critical_failures: [] when no critical failure is evidenced. Scores range from 0 to 5.
Do not add type annotations, list=, duplicate evaluations, or prose outside JSON.
'''

CRITICAL_REVIEW_RULES = '''
# MANDATORY FAILURE RULES
For the evaluated agent, set its score to 0 and report a critical_failures item
with agent, code, and concrete code/output evidence when any of these occurs:
- FABRICATED_METRIC: hardcoded or invented numbers presented as measured validation metrics.
- FABRICATED_PREDICTION: random/placeholder outputs presented as trained-model predictions.
- REQUIRED_STEP_MISSING: required training, validation, prediction or tool execution is
  skipped, simulated or claimed complete without execution evidence.
- EXECUTION_FAILED: the current code execution or required tests failed.
- DATA_INTEGRITY: target labels, test IDs or row alignment are corrupted.
Do not infer success from printed claims or the existence of an output file alone.
Check the supplied execution evidence. An explicitly labelled random baseline,
fixed seed, stochastic model, or legitimate not-applicable statistic is not fabrication.
A hypothetical concern is not evidence: give actionable suggestions instead.
Each role must score at least 3; another role's score cannot offset a failure.
'''
PROMPT_REVIEWER_ROUND0 += CRITICAL_REVIEW_RULES
