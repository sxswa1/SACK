from typing import Dict, Any, List, Tuple
import json
import re
import logging
import os

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
from sack.Agents.agent_summarizer import Summarizer
from sack.state import State
from sack.runtime_support import ReplyFormatError, missing_insight_fields, parse_json_object
from sack.Prompts.prompt_summarizer import *
from sack.Prompts.eda_prompt.prompt_summarizer import PROMPT_EDAINSIGHT_POPULATION_WITH_TOOLS
from sack.EDAInsightPrompts.edainsight_template import EDAInsightTemplate


class EDASummarizer(Summarizer):
    def __init__(self, model: str, type: str):
        super().__init__(
            model=model,
            type=type
        )
        self.tool_field_mapping = {
            "pre_eda":{
                # 数据质量相关工具
                "calculate_overall_missing_rate": "data_quality.missingness.overall_missing_rate",
                "analyze_column_missing_distribution": "data_quality.missingness.column_missing_distribution",
                "analyze_row_completeness": "data_quality.missingness.row_completeness",
                "detect_missing_pattern_type": "data_quality.missingness.missing_pattern_type",
                "detect_outliers": ["data_quality.outliers.outlier_columns_ratio",
                                    "data_quality.outliers.avg_outlier_ratio"],
                "classify_outlier_severity": "data_quality.outliers.outlier_severity_distribution",
                "check_data_type_consistency": "data_quality.data_integrity.type_violation_ratio",
                "check_uniqueness_constraints": "data_quality.data_integrity.unique_violation_ratio",

                # 分布相关工具
                "analyze_numerical_skewness": "basic_distribution.numerical.skewness_profile",
                "analyze_numerical_scale": "basic_distribution.numerical.scale_characteristics",
                "test_normality": "basic_distribution.numerical.normality_assessment",
                "detect_multimodal_distributions": "basic_distribution.numerical.multimodal_assessment",
                "analyze_categorical_cardinality": "basic_distribution.categorical.cardinality_pattern",
                "calculate_cardinality_variance": "basic_distribution.categorical.cardinality_pattern",
                "analyze_categorical_imbalance": "basic_distribution.categorical.imbalance_profile",
                "detect_rare_categories": "basic_distribution.categorical.rare_categories",

                # 维度相关工具
                "calculate_samples_per_feature": "basic_dimensionality.samples_per_feature",
            },
            "deep_eda":{
                # 深度EDA工具
                "analyze_numerical_correlation_strength": "feature_relationships.correlation_structure.correlation_strength",
                "detect_correlation_clusters": "feature_relationships.correlation_structure.correlation_clustering",
                "detect_multicollinearity_vif": "feature_relationships.correlation_structure.multicollinearity",
                "detect_redundant_feature_pairs": "feature_relationships.correlation_structure.multicollinearity",
                "analyze_feature_target_relationship_classification": "feature_relationships.target_relationship.feature_importance_distribution",
                "analyze_feature_target_relationship_regression": "feature_relationships.target_relationship.feature_importance_distribution",
                "detect_interaction_effects": "feature_relationships.target_relationship.interaction_with_target",
                "quantify_synergistic_interactions": "feature_relationships.interaction_patterns.synergistic_interactions",
                "quantify_categorical_numerical_interaction": "feature_relationships.interaction_patterns.categorical_numerical_interaction",
                "detect_conditional_dependencies": "feature_relationships.interaction_patterns.conditional_dependencies",
                "detect_nonlinear_relationships": "feature_relationships.interaction_patterns.nonlinear_relationships",
                "assess_dataset_complexity": "complexity",
                "calculate_samples_per_feature": "complexity.dimensionality.samples_per_feature",
                "estimate_feature_interaction_potential": "complexity.dimensionality.feature_interaction_potential",
                "analyze_sparsity": ["complexity.sparsity_patterns.zero_dominated_ratio",
                                    "complexity.sparsity_patterns.sparse_columns_ratio"],
                "estimate_signal_to_noise": "complexity.noise_level.signal_to_noise_estimate",
                "estimate_inherent_uncertainty": "complexity.noise_level.inherent_uncertainty",
                "analyze_time_series_properties": "special_scenarios.temporal_properties",
                "estimate_causal_confounder_strength": "special_scenarios.causal_properties",
                "analyze_spatial_correlation": "special_scenarios.spatial_properties",
                "analyze_high_cardinality_impact": "special_scenarios.high_cardinality_impact"
            }
        }

    def _generate_eda_insight_templates(self, eda_phase):
        """Initialize the EDA summarizer."""
        if eda_phase=="PEDA Insight Extraction":
            template_key = "pre_eda"
        else:
            template_key = "deep_eda"
        target_template = EDAInsightTemplate[template_key]


        # 递归把模板字段设为 unknown，仅保留当前阶段结构。
        def set_unknown(template):
            if isinstance(template, dict):
                return {k: set_unknown(v) for k, v in template.items()}
            elif isinstance(template, list):
                return [set_unknown(item) for item in template]
            else:
                return "unknown"

        eda_template_with_unknown = set_unknown(target_template)

        return {
            "description": f"Fixed EDAInsight template ({template_key}) for {eda_phase}",
            "template": eda_template_with_unknown,
            "tools_mapping": self.tool_field_mapping,
            "original_template": target_template,
            "template_key": template_key
        }


    # 获取所有之前智能体的输出的可参考内容
    def _extract_eda_specific_information(self, state: State) -> Dict[str, Any]:
        """Load EDA analysis content."""
        with open(f'{state.restore_dir}/markdown_plan.txt', 'r', encoding='utf-8') as f:
            plan = f.read()

        with open(f'{state.restore_dir}/single_phase_code.txt', 'r', encoding='utf-8') as f:
            code = f.read()

        with open(f'{state.restore_dir}/{state.dir_name}_output.txt', 'r', encoding='utf-8') as f:
            code_output = f.read()

        with open(f'{state.restore_dir}/review.json', 'r', encoding='utf-8') as f:
            review = json.load(f)

        visual_insights = self._get_insight_from_visualization(state)

        # 获取当前阶段的工具上下文。
        tools, tool_names = self._get_tools(state)
        tool_context = {
            "tool_list": tool_names,
            "tool_descriptions": tools
        }

        return {
            "plan": plan,
            "code": code,
            "code_output": code_output,
            "review": review,
            "visual_insights": visual_insights,
            "tool_context": tool_context
        }


    def _validate_eda_insight(self, state: State, eda_insight: Dict[str, Any], eda_info: Dict[str, Any]) -> Dict[str, Any]:
        """Build the template key mapping."""
        eda_phase = state.phase
        template_key = "pre_eda" if eda_phase == "PEDA Insight Extraction" else "deep_eda"
        # 统一预期字段。
        unknown_count = self._count_unknown_fields(eda_insight)
        total_fields = self._count_total_fields(eda_insight)

        # 统计未知字段
        tool_list = eda_info["tool_context"]["tool_list"]
        tool_output_extraction = self._validate_tool_output_extraction(eda_insight, tool_list, template_key)

        validation_result = {
            "completeness_score": round((total_fields - unknown_count) / total_fields * 5, 1) if total_fields > 0 else 0,
            "unknown_fields_count": unknown_count,
            "total_fields_count": total_fields,
            "tool_output_validation": tool_output_extraction,  # 工具输出验证结果
            "recommendations": self._generate_validation_recommendations(unknown_count, total_fields, tool_output_extraction)
        }

        return validation_result

    def _validate_tool_output_extraction(self, eda_insight: Dict[str, Any], tool_list: List[str], template_key: str) -> \
    Dict[str, Any]:
        """Extract insight template data."""
        validation = {
            "extracted_tools": [],
            "missing_tool_outputs": [],
            "partial_extraction_tools": [],
            "tool_validation_details": {}
        }

        # 先获取当前阶段的工具映射层
        current_phase_tool_mapping = self.tool_field_mapping.get(template_key, {})

        for tool in tool_list:
            if tool not in current_phase_tool_mapping:  # 改为检查当前阶段的映射层
                validation["tool_validation_details"][tool] = {
                    "status": "no_mapping",
                    "message": f"No mapped fields in {template_key} template"
                }
                continue

            # 获取工具对应的字段路径（从当前阶段映射层取）
            field_paths = current_phase_tool_mapping[tool]
            if not isinstance(field_paths, list):
                field_paths = [field_paths]

            tool_validation = {
                "total_fields": len(field_paths),
                "extracted_fields": 0,
                "missing_fields": [],
                "status": ""
            }

            # 检查每个字段的填充情况（逻辑不变）
            for field_path in field_paths:
                field_value = self._get_nested_value(eda_insight, field_path)

                if field_value == "unknown" or field_value is None:
                    tool_validation["missing_fields"].append(field_path)
                else:
                    if isinstance(field_value, (dict, list)):
                        sub_unknown = self._count_unknown_fields(field_value)
                        sub_total = self._count_total_fields(field_value)
                        if sub_unknown < sub_total:
                            tool_validation["extracted_fields"] += 1
                        else:
                            tool_validation["missing_fields"].append(field_path)
                    else:
                        tool_validation["extracted_fields"] += 1

            # 判定工具提取状态（逻辑不变）
            if tool_validation["extracted_fields"] == 0:
                tool_validation["status"] = "missing"
                validation["missing_tool_outputs"].append(tool)
            elif tool_validation["extracted_fields"] < tool_validation["total_fields"]:
                tool_validation["status"] = "partial"
                validation["partial_extraction_tools"].append(tool)
            else:
                tool_validation["status"] = "complete"
                validation["extracted_tools"].append(tool)

            validation["tool_validation_details"][tool] = tool_validation

        return validation

    def _generate_validation_recommendations(self, unknown_count: int, total_fields: int, tool_validation: Dict) -> \
    List[str]:
        """Generate EDA insight content."""
        recommendations = []

        # 完整性建议
        completeness_ratio = (total_fields - unknown_count) / total_fields if total_fields > 0 else 0
        if completeness_ratio < 0.6:
            recommendations.append(
                f"Low overall completeness ({completeness_ratio:.1%}) - enhance extraction from tool outputs")

        # 工具输出建议。
        missing_tools = tool_validation.get("missing_tool_outputs", [])
        if missing_tools:
            recommendations.append(f"Missing output extraction for critical tools: {', '.join(missing_tools)}")

        partial_tools = tool_validation.get("partial_extraction_tools", [])
        if partial_tools:
            recommendations.append(f"Partial output extraction for tools: {', '.join(partial_tools)}")

        return recommendations

    def _count_unknown_fields(self, obj, path="") -> int:
        """Read JSON data."""
        count = 0
        if isinstance(obj, dict):
            for key, value in obj.items():
                current_path = f"{path}.{key}" if path else key
                if value == "unknown":
                    count += 1
                elif isinstance(value, (dict, list)):
                    count += self._count_unknown_fields(value, current_path)
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                current_path = f"{path}[{i}]"
                if item == "unknown":
                    count += 1
                elif isinstance(item, (dict, list)):
                    count += self._count_unknown_fields(item, current_path)
        return count

    def _count_total_fields(self, obj) -> int:
        """Read text data."""
        count = 0
        if isinstance(obj, dict):
            for value in obj.values():
                count += 1
                if isinstance(value, (dict, list)):
                    count += self._count_total_fields(value)
        elif isinstance(obj, list):
            for item in obj:
                count += 1
                if isinstance(item, (dict, list)):
                    count += self._count_total_fields(item)
        return count

    def _get_nested_value(self, obj, path: str):
        """Generate a prompt for the current context."""
        keys = path.split('.')
        current = obj
        for key in keys:
            if '[' in key and ']' in key:
                list_key = key.split('[')[0]
                index = int(key.split('[')[1].split(']')[0])
                if list_key in current and isinstance(current[list_key], list) and len(current[list_key]) > index:
                    current = current[list_key][index]
                else:
                    return None
            elif key in current:
                current = current[key]
            else:
                return None
        return current

    def _save_eda_insight_results(self, state: State, eda_insight_with_evidence: Dict, eda_insight: Dict,
                                  validation_result: Dict):
        """Validate EDAInsight output."""
        with open(f'{state.restore_dir}/eda_insight_with_evidence.json', 'w', encoding='utf-8') as f:
            json.dump(eda_insight_with_evidence, f, ensure_ascii=False, indent=2)

        with open(f'{state.restore_dir}/eda_insight.json', 'w', encoding='utf-8') as f:
            json.dump(eda_insight, f, ensure_ascii=False, indent=2)

        with open(f'{state.restore_dir}/eda_insight_validation.json', 'w', encoding='utf-8') as f:
            json.dump(validation_result, f, ensure_ascii=False, indent=2)

    def _extract_clean_eda_insight(self, raw_response: str, template: Dict) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """Populate EDAInsight fields."""
        try:
            response_with_evidence = parse_json_object(raw_response)
            clean_insight = self._remove_evidence_fields(response_with_evidence, template)
            return response_with_evidence, clean_insight
        except ReplyFormatError as exc:
            logger.error("Failed to parse EDAInsight JSON: %s", exc)
            logger.error("Raw response preview: %s", raw_response[:500])
            # Validation rejects the unknown template; do not accept a list or
            # silently merge multiple JSON objects into one insight.
            return template, template

    def _remove_evidence_fields(self, data: Any, template: Any) -> Any:
        """Read the summary report."""
        if isinstance(data, dict):
            # 处理证据包的结构。
            if "value" in data and "_evidence" in data and len(data) == 2:
                return data["value"]

            cleaned = {}
            for key, value in data.items():
                # 处理证据包装结构
                if key.endswith("_evidence"):
                    continue
                template_sub = template.get(key, {}) if isinstance(template, dict) else {}
                cleaned[key] = self._remove_evidence_fields(value, template_sub)
            return cleaned
        elif isinstance(data, list):
            template_sub = template[0] if (isinstance(template, list) and template) else {}
            return [self._remove_evidence_fields(item, template_sub) for item in data]
        else:
            return data

    def _populate_eda_insight(self, state: State) -> Dict[str, Any]:
        """Merge summary and EDAInsight output."""
        eda_phase = state.phase
        if not eda_phase:
            return None

        # 生成固定模板（仅值为unknown）
        templates = self._generate_eda_insight_templates(eda_phase)
        template = templates["template"]
        template_json = json.dumps(template, indent=2)
        template_key = templates["template_key"]

        # 获取EDA信息（含工具上下文）
        eda_info = self._extract_eda_specific_information(state)
        tool_context = json.dumps(eda_info["tool_context"], indent=2)
        current_tools = eda_info["tool_context"]["tool_list"]

        # 生成工具到字段的映射表，用于提示词。

        tool_mapping_table = "| Tool Name | Mapped EDAInsight Fields |\n|-----------|--------------------------|\n"
        # 先获取当前阶段的工具映射层
        current_phase_tool_mapping = self.tool_field_mapping.get(template_key, {})
        for tool in current_tools:
            if tool in current_phase_tool_mapping:
                field_paths = current_phase_tool_mapping[tool]
                if isinstance(field_paths, list):
                    fields_str = "<br>".join(field_paths)
                else:
                    fields_str = field_paths
                tool_mapping_table += f"| {tool} | {fields_str} |\n"
            else:
                tool_mapping_table += f"| {tool} | No mapped fields in {template_key} template |\n"
        population_prompt = PROMPT_EDAINSIGHT_POPULATION_WITH_TOOLS.format(tool_mapping_table=tool_mapping_table,
                                                                           eda_insight_template=template_json,
                                                                           current_phase_tools=", ".join(current_tools),
                                                                           tool_context=tool_context,
                                                                           plan=eda_info["plan"],
                                                                           code_output=eda_info["code_output"],
                                                                           review=json.dumps(eda_info["review"],indent=2),
                                                                           visual_insights=eda_info["visual_insights"])
        max_retries = 3  # 最大重试次数
        retry_count = 0
        populated_with_evidence_raw = None
        is_success = False
        while retry_count < max_retries and not is_success:
            # 每次重试重置对话历史，避免历史累积影响结果
            population_history = []
            try:
                # 调用LLM生成结果
                populated_with_evidence_raw, population_history = self.llm.generate(
                    population_prompt,
                    population_history,
                    max_completion_tokens=8192
                )
                # 检查返回结果是否有效。
                if populated_with_evidence_raw and populated_with_evidence_raw.strip():
                    is_success = True
                else:
                    retry_count += 1
                    logger.warning(
                        f"LLM杩斿洖绌哄搷搴旓紝閲嶈瘯娆℃暟: {retry_count}/{max_retries} | 闃舵: {eda_phase}"
                    )
            except Exception as e:
                retry_count += 1
                logger.error(
                    f"LLM调用失败，重试次数: {retry_count}/{max_retries} | 阶段: {eda_phase} | 异常: {str(e)}",
                    exc_info=True  # 打印完整堆栈，便于排查
                )
                populated_with_evidence_raw = None

        if is_success:
            # 解析并提取纯净的 EDAInsight。
            populated_insight_with_evidence, populated_insight = self._extract_clean_eda_insight(
                populated_with_evidence_raw, template
            )
        else:
            logger.error(
                f"LLM调用耗尽{max_retries}次重试仍失败，使用原始模板 | 阶段: {eda_phase}"
            )
            populated_insight_with_evidence = template
            populated_insight = template
        # 验证质量（基于工具输出）
        validation_result = self._validate_eda_insight(state, populated_insight, eda_info)
        validation_result['missing_schema_fields'] = missing_insight_fields(template, populated_insight)
        # 保存结果
        self._save_eda_insight_results(state, populated_insight_with_evidence, populated_insight, validation_result)
        return populated_insight

    def _execute(self, state: State, role_prompt: str) -> Dict[str, Any]:
        if state.memory[-1].get("developer", {}).get("status", True) == False: # 代码有问题的不需要总结，因为下一轮还需要重新代码生成
            print(f"State {state.phase} - Agent {self.role} gives up summarizing because the code execution failed.")
            return {self.role: {"eda_insight": {}}}

        # EDAInsight濉厖
        eda_insight = self._populate_eda_insight(state)
        with open(f'{state.restore_dir}/eda_insight_validation.json', encoding='utf-8') as output:
            validation = json.load(output)
        missing_tools = validation.get('tool_output_validation', {}).get('missing_tool_outputs', [])
        quality_valid = not (validation.get('unknown_fields_count', 0) or
                             validation.get('missing_schema_fields') or missing_tools)
        if not quality_valid:
            template_key = 'pre_eda' if state.phase == 'PEDA Insight Extraction' else 'deep_eda'
            required_tools = set(missing_tools)
            for tool, paths in self.tool_field_mapping.get(template_key, {}).items():
                paths = [paths] if isinstance(paths, str) else paths
                if any(field == path or field.startswith(path + '.')
                       for field in validation.get('missing_schema_fields', [])
                       for path in paths):
                    required_tools.add(tool)
            advice = ('EDA insight is incomplete. Generate and print the required tool outputs. '
                      f'Tools needed for missing or partial results: {sorted(required_tools)}; missing fields: '
                      f"{validation.get('missing_schema_fields', [])}; "
                      f"unknown fields: {validation.get('unknown_fields_count', 0)}")
            suggestions = state.memory[-1].get('reviewer', {}).setdefault('suggestion', {})
            for role in ('agent planner', 'agent developer'):
                suggestions[role] = suggestions.get(role, '') + '\n' + advice

        result = {
            self.role: {
                "eda_insight": eda_insight,
                "quality_valid": quality_valid,
            }
        }
        return result
