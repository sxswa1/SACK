import json
import logging
import os
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
import re
import pandas as pd

from sack.paths import (
    COMPETITION_DATA_DIR,
    EDA_COMPETITION_DATA_DIR,
    PROJECT_ROOT,
    ensure_project_imports,
)
from sack.LLMComponent.llm import OpenaiEmbeddings, LLM
from sack.state import State

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
current_file_path = os.path.abspath(__file__)
current_project_dir = os.path.dirname(os.path.dirname(current_file_path))
ensure_project_imports()

MODULE_WEIGHTS = {
    "pre_eda": {
        "data_quality": 0.4,
        "basic_distribution": 0.5,
        "basic_dimensionality": 0.1
    },
    "deep_eda": {
        "feature_relationships": 0.45,
        "complexity": 0.35,
        "special_scenarios": 0.2
    }
}

class SACKCaseRetriever():
    def __init__(self,
                 kg_endpoint: str = 'http://localhost:7200',
                 kg_db: str = 'kaggle',
                 **pg_kwargs):
        try:
            from sack.knowledge.api.api import SACKKnowledgeBase
            self.sack_knowledge = SACKKnowledgeBase(
                endpoint=kg_endpoint,
                db=kg_db, **pg_kwargs
            )
            print("SACKKnowledgeBase client initialized.")
        except ModuleNotFoundError as e:
            print(f"SACKKnowledgeBase import failed: {e}")
            raise
        except Exception as e:
            print(f"SACKKnowledgeBase initialization failed: {e}")
            raise

        self.llm = LLM(model = "qwen-plus", type="api")
        self.last_retrieval_error: Optional[str] = None

    # TODO: 直接在提取核心见解的时候就用对应的名字，可以避免映射
    PHASE_MAPPING = {
        "Preliminary Exploratory Data Analysis": "Preliminary EDA",
        "Data Cleaning": "Data Cleaning",
        "In-depth Exploratory Data Analysis": "In-depth EDA",
        "Feature Engineering": "Feature Engineering",
        "Model Building, Validation, and Prediction": "Model Building and Prediction"
    }


    def get_current_comp_path(self, state: State):
        """从状态中获取当前竞赛的本地路径，用于相似性检索"""
        raw_competition = str(state.competition)
        raw_path = Path(raw_competition).expanduser()
        if raw_path.is_absolute() and raw_path.exists():
            competition_path = raw_path.resolve()
            competition = competition_path.name
        else:
            project_relative_path = (PROJECT_ROOT / raw_path).resolve()
            if project_relative_path.exists():
                competition_path = project_relative_path
                competition = competition_path.name
            else:
                competition = raw_path.name
                competition_path = COMPETITION_DATA_DIR / competition
        if not competition_path.exists():
            raise FileNotFoundError(f"Current competition source data path not found: {competition_path}")

        return competition, str(competition_path)

    def get_phase_similar_weights(self,state:State):
        if state.phase == "Preliminary Exploratory Data Analysis":
            eda_weights = None
            final_similar_weight = {"base_similar":1,"eda_similar":0}
        elif state.phase == "Data Cleaning":
            eda_weights = {"pre_eda":1,"deep_eda":0}
            final_similar_weight = {"base_similar":0.2,"eda_similar":0.8}
        elif state.phase == "In-depth Exploratory Data Analysis":
            eda_weights = {"pre_eda":1,"deep_eda":0}
            final_similar_weight = {"base_similar":0.5,"eda_similar":0.5}
        elif state.phase == "Feature Engineering":
            eda_weights = {"pre_eda":0.3,"deep_eda":0.7}
            final_similar_weight = {"base_similar":0.3,"eda_similar":0.7}
        elif state.phase == "Model Building, Validation, and Prediction":
            eda_weights = {"pre_eda":0.3,"deep_eda":0.7}
            final_similar_weight = {"base_similar":0.6,"eda_similar":0.4}
        else:
            eda_weights = None
            final_similar_weight = None
        return eda_weights, final_similar_weight

    def get_recall_k(self, k: int) -> int:
        """
        召回足够多的候选，以免重排后候选不足。
        最小10，默认取 max(10, 3*k)。
        """
        return max(10, 3 * k)
    
    def retrieve_similar_competitions(self, state: State, k: int = 5, retrieval_mode: str = "weighted_topk") -> List[Dict]:
        """检索与当前竞赛相似的 Top-k 历史竞赛"""
        self.last_retrieval_error = None
        try:
            similar_df_cache_path = os.path.join(state.competition_dir, "similar_competitions_df.csv")
            similar_df = None
            if os.path.exists(similar_df_cache_path):
                try:
                    # 读取CSV缓存，保留所有原始字段
                    similar_df = pd.read_csv(similar_df_cache_path, encoding="utf-8")
                    logger.info("Loaded similar competition cache: %s", similar_df_cache_path)
                except Exception as e:
                    logger.warning("Failed to read similar competition cache; recomputing: %s", e)
                    similar_df = None
            if similar_df is None:
                competition,current_comp_path = self.get_current_comp_path(state)
    
                # 获取当前竞赛的profile
                current_comp_profile = self.sack_knowledge.generate_competition_profile(
                    comp_id=competition,
                    persist_path=current_comp_path,
                    source_path=current_comp_path,
                )
    
    
                # 调用 SACKKnowledgeBase API 获取基础相似竞赛。
                base_similar_df = self.sack_knowledge.get_top_k_similar_competitions(
                    current_comp=current_comp_profile,
                    return_all=True,
                    show_query=False
                )
                eda_similar_df = self.sack_knowledge.get_top_k_edainsight_similar_competitions(
                    current_comp=current_comp_profile,
                    return_all=True,
                    show_query=False
                )
    
                # 外连接原始相似度数据，不加入阶段权重。
                merge_key = "Competition_ID"
                if merge_key not in base_similar_df.columns:
                    logger.warning("Base similarity result is empty or missing %s.", merge_key)
                    return []
                if merge_key not in eda_similar_df.columns:
                    logger.warning("EDA similarity result is empty or missing %s; using base similarity only.", merge_key)
                    eda_similar_df = pd.DataFrame({merge_key: base_similar_df[merge_key]})
                # 外连接生成原始数据（仅含原始相似度，无加权字段）
                base_cols = [merge_key, "Total_Score", "Semantic_Score", "Fused_Data_Score"]
                base_cols = [col for col in base_cols if col in base_similar_df.columns]
                eda_cols = list(eda_similar_df.columns)
                # 外连接生成原始数据（仅含原始相似度，无加权字段）
                similar_df = base_similar_df[base_cols].merge(
                    eda_similar_df[eda_cols],
                    on=merge_key,
                    how="outer"  # 外连接：保留两个df中的所有竞赛
                )
    
                # 原始字段缺失值填充（所有数值型字段填0）
                for col in similar_df.columns:
                    if col != merge_key and pd.api.types.is_numeric_dtype(similar_df[col]):
                        similar_df[col] = similar_df[col].fillna(0.0).round(3)
    
                # 将原始相似度数据保存为 CSV 缓存。
                try:
                    # 确保目录存在。
                    os.makedirs(state.competition_dir, exist_ok=True)
                    # 保存 CSV 时不写索引，并使用 UTF-8 编码。
                    similar_df.to_csv(similar_df_cache_path, index=False, encoding="utf-8")
                    logger.info(f"鎴愬姛淇濆瓨鐩镐技搴︾紦瀛橈細{similar_df_cache_path}")
                except Exception as e:
                    logger.warning("Failed to save similar competition cache: %s", e)
    
            if retrieval_mode=="weighted_topk":
                # ========== 动态计算加权后的EDA_Similarity（核心逻辑） ==========
                eda_weights, final_similar_weight = self.get_phase_similar_weights(state)
                base_weight = final_similar_weight["base_similar"]
                eda_weight = final_similar_weight["eda_similar"]

                current_similar_df = similar_df.copy()

                # 初始化 EDA_Similarity 字段。
                current_similar_df["EDA_Similarity"] = 0.0
                # 计算 EDA 类型权重总和，用于归一化。
                if eda_weights is not None and final_similar_weight is not None:
                    total_eda_type_weight = sum([w for w in eda_weights.values() if w > 0])

                    if total_eda_type_weight > 0:
                        # 遍历每个EDA类型（pre_eda/deep_eda）及其权重
                        for eda_type, type_weight in eda_weights.items():
                            if type_weight <= 0:
                                continue
                            # 匹配该EDA类型下的所有模块字段（如pre_eda_data_overview）
                            module_fields = [col for col in current_similar_df.columns if col.startswith(f"{eda_type}_")]
                            # 按模块权重累加相似度。
                            for field in module_fields:
                                # 提取模块名（如pre_eda_data_overview → data_overview）
                                module_name = field.replace(f"{eda_type}_", "")
                                # 获取模块权重（从全局MODULE_WEIGHTS配置中取）
                                module_weight = MODULE_WEIGHTS.get(eda_type, {}).get(module_name, 1.0)
                                # 模块相似度乘以 EDA 类型权重和模块权重后累加。
                                current_similar_df["EDA_Similarity"] += current_similar_df[field] * type_weight * module_weight

                    # 归一化 EDA_Similarity，避免权重总和不为 1。
                    if total_eda_type_weight > 0:
                        current_similar_df["EDA_Similarity"] = current_similar_df["EDA_Similarity"] / total_eda_type_weight
                    else:
                        current_similar_df["EDA_Similarity"] = 0.0

                    # 计算最终融合相似度。
                    current_similar_df["final_similarity"] = (
                            current_similar_df["Total_Score"] * base_weight +
                            current_similar_df["EDA_Similarity"] * eda_weight
                    )
                elif eda_weights == None and final_similar_weight is not None: # 初步数据探索阶段只考虑浅层相似度
                    current_similar_df["final_similarity"] = current_similar_df["Total_Score"]
                else:
                    raise ValueError(f"Phase {state.phase} does not support similarity retrieval!")


                current_similar_df = current_similar_df.sort_values(by="final_similarity", ascending=False).head(k).reset_index(drop=True)
            elif retrieval_mode == "recall_rerank":
                # ========== 计算最终融合相似度 ==========
                eda_weights, final_similar_weight = self.get_phase_similar_weights(state)

                current_similar_df = similar_df.copy()

                # --------- 1) Recall：仅用浅层相似度 Total_Score 召回候选 ---------
                recall_k = self.get_recall_k(k)
                # 若缺失 Total_Score 列，直接报错（你当前base_cols保证了它通常存在）
                if "Total_Score" not in current_similar_df.columns:
                    raise ValueError("Missing 'Total_Score' in similar_df, cannot perform recall.")
                recall_df = (
                    current_similar_df
                    .sort_values(by="Total_Score", ascending=False)
                    .head(recall_k)
                    .reset_index(drop=True)
                )

                # --------- 2) Rerank：在候选集上按阶段计算 EDA_Similarity 并排序 ---------
                # 初步 EDA 阶段不使用 EDA 相似度，仅按 Total_Score 排序。
                recall_df["EDA_Similarity"] = 0.0

                if eda_weights is not None:
                    # 计算 EDA 类型权重总和，用于归一化。
                    total_eda_type_weight = sum([w for w in eda_weights.values() if w > 0])
                    if total_eda_type_weight > 0:
                        for eda_type, type_weight in eda_weights.items():
                            if type_weight <= 0:
                                continue

                            # 仅使用当前 EDA 类型相关字段。
                            module_fields = [col for col in recall_df.columns if col.startswith(f"{eda_type}_")]

                            for field in module_fields:
                                # 提取模块名，沿用原有权重逻辑。
                                module_name = field.replace(f"{eda_type}_", "")
                                module_weight = MODULE_WEIGHTS.get(eda_type, {}).get(module_name, 1.0)
                                recall_df["EDA_Similarity"] += recall_df[field] * type_weight * module_weight

                        recall_df["EDA_Similarity"] = recall_df["EDA_Similarity"] / total_eda_type_weight

                    # Rerank：先按EDA_Similarity，再用Total_Score做tie-breaker
                    rerank_df = (
                        recall_df
                        .sort_values(by=["EDA_Similarity", "Total_Score"], ascending=[False, False])
                        .head(k)
                        .reset_index(drop=True)
                    )
                else:
                    # 不需要EDA重排的阶段：直接按Total_Score输出Top-k
                    rerank_df = (
                        recall_df
                        .sort_values(by="Total_Score", ascending=False)
                        .head(k)
                        .reset_index(drop=True)
                    )
                if eda_weights is not None:
                    rerank_df["final_similarity"] = rerank_df["EDA_Similarity"]
                else:
                    rerank_df["final_similarity"] = rerank_df["Total_Score"]

                current_similar_df = rerank_df
            else:
                raise ValueError(f"Unknown retrieval_mode: {retrieval_mode}")
    
    
            # 转换为字典列表，并补充竞赛背景信息。
            similar_comps = []
            for idx, row in current_similar_df.iterrows():
                comp_id = row["Competition_ID"]
                print(comp_id)
                # 此处可扩展为从知识图谱获取竞赛描述。
                # 【关键修改】：处理所有可能的字段缺失，补充融合后的字段
                similar_comps.append({
                    "competition_id": comp_id,
                    "base_total_score": row["Total_Score"],  # 宏观总得分
                    "eda_similar_score": row["EDA_Similarity"],  # 微观EDA相似度（防护缺失）
                    "final_similarity": row["final_similarity"],  # 融合后的最终相似度 可以是召回-重排序模式的分数，也可以是加权分数
                    "rank": idx + 1,  # 排名从1开始（原逻辑是0，不符合常规排名习惯）
                    "overview": self.sack_knowledge.get_competition_field(competition_uri=comp_id, field="overview")
                })
    
            logger.info(f"Retrieved {len(similar_comps)} similar competitions")
            return similar_comps
        except Exception as e:
            self.last_retrieval_error = str(e)
            logger.error("Failed to retrieve similar competitions: %s", e, exc_info=True)
            return []

    def retrieve_core_insights(self,competitions, top_pipelines_per_comp: int = 3) -> Dict:
        """Retrieve core insights from top pipelines for each similar competition."""
        if not competitions:
            logger.warning("No competitions to retrieve insights from")
            return {}
        core_insights= {}
        for comp in competitions:
            comp_id = comp["competition_id"]
            # 1. 获取该竞赛的top-N解决方案（pipeline URI）
            pipelines = self._get_top_pipelines_for_competition(comp_id, top_pipelines_per_comp)
            if not pipelines:
                continue

            # 2. 为每个pipeline检索核心见解
            for pipeline_uri in pipelines:
                try:
                    insights_df = self.sack_knowledge.get_core_insights_for_pipeline(
                        pipeline_uri=pipeline_uri,
                        show_query=False
                    )
                    # 转换为字典列表
                    insights = insights_df.to_dict("records")
                    if insights:
                        core_insights[pipeline_uri] = {
                            "competition_id": comp_id,
                            "insights": insights
                        }
                        logger.info(f"Retrieved {len(insights)} insights for pipeline {pipeline_uri}")
                except Exception as e:
                    logger.error(f"Failed to retrieve insights for {pipeline_uri}: {str(e)}")

        return core_insights

    def _get_top_pipelines_for_competition(self, comp_id: str, top_n: int) -> List[str]:
        """Return top pipeline URIs for a competition."""
        # 示例：调用SACKKnowledgeBase的get_top_k_scoring_pipelines_for_dataset（假设comp_id对应dataset）
        pipelines_df = self.sack_knowledge.get_top_k_scoring_pipelines_for_dataset(
            dataset=comp_id,
            k=top_n,
            show_query=False
        )
        if not pipelines_df.empty and "Pipeline_id" in pipelines_df.columns:
            return pipelines_df["Pipeline_id"].tolist()
        return []

    def integrate_insights(self, similar_comps, core_insights) -> Dict[str, Any]:
        """Integrate similar competitions and retrieved core insights."""
        if not similar_comps and not core_insights:
            return {"message": "No relevant cases found in SACKKnowledgeBase"}

        # 按竞赛分组整合见解
        comp_insights = {}
        for comp in similar_comps:
            comp_id = comp["competition_id"]  # 竞赛URI（如http://sack.local/resource/kaggle/playground-series-s3e11）
            comp_insights[comp_id] = {
                "competition_info": comp,
                "pipelines": []
            }

        for pipeline_uri, info in core_insights.items():
            comp_id = info["competition_id"]  # 所属竞赛的 URI。
            comp_uri_prefix = comp_id  # 竞赛URI作为前缀（如http://sack.local/resource/kaggle/playground-series-s3e11）
            if pipeline_uri.startswith(comp_uri_prefix):
                pipeline_id = pipeline_uri[len(comp_uri_prefix) + 1:]  # 去除 URI 前缀和分隔符。
            else:
                # 异常处理：若URI格式不匹配，取最后一段作为fallback
                pipeline_id = pipeline_uri.split('/')[-1]
                logger.warning("Unexpected pipeline_uri format; using fallback ID %s for URI %s", pipeline_id, pipeline_uri)

            # 为每个insight关联规范ID
            formatted_insights = []
            for insight in info["insights"]:
                formatted_insights.append({
                    # 保留原始字段和规范 ID。
                    **insight
                })

            # 将带规范 ID 的 Pipeline 加入竞赛分组。
            comp_insights[comp_id]["pipelines"].append({
                "pipeline_id": pipeline_id,  # 规范的 Pipeline ID。
                "insights": formatted_insights
            })
        return comp_insights

    def gated_insights(self, comp_insights: Dict[str, Any], state: State) -> Dict[str, Any]:
        """
        Hybrid Gate:
        1) Phase prefilter
        2) Hard Gate: 用规则拦截明显不适用的经验
        3) Soft Gate: LLM做适用性判断(按 competition 批量做)
        """
        if not comp_insights or "message" in comp_insights:
            return comp_insights

        current_phase = getattr(state, "phase", None)
        if not current_phase:
            return {"message": "Missing current phase in state, cannot perform gating."}

        gate_context = self._build_gate_context_from_state(state)

        # 按当前阶段预过滤 CoreInsight。
        phase_prefiltered = self._prefilter_insights_by_phase(comp_insights, current_phase)
        if not phase_prefiltered or "message" in phase_prefiltered:
            return phase_prefiltered

        gated_result = {}
        gate_summary = {
            "phase": current_phase,
            "total_candidates": 0,
            "hard_dropped": 0,
            "soft_keep": 0,
            "soft_warn": 0,
            "soft_drop": 0,
            "final_kept": 0,
            "hard_kept": 0
        }

        for comp_id, comp_data in phase_prefiltered.items():
            competition_info = comp_data.get("competition_info", {})
            pipelines = comp_data.get("pipelines", [])

            # -----------------------------------
            # Step 2. Hard Gate（逐条）
            # 先保留通过 Hard Gate 的候选，再按竞赛执行 Soft Gate。
            # -----------------------------------
            hard_kept_candidates = []  # competition级别候选池
            hard_gate_meta_by_pipeline = {}  # pipeline_id -> [meta...]

            for pipeline in pipelines:
                pipeline_id = pipeline.get("pipeline_id", "")
                insights = pipeline.get("insights", [])

                if pipeline_id not in hard_gate_meta_by_pipeline:
                    hard_gate_meta_by_pipeline[pipeline_id] = []

                for insight in insights:
                    gate_summary["total_candidates"] += 1

                    hard_decision, hard_meta = self._hard_gate_single_insight(
                        insight=insight,
                        gate_context=gate_context,
                        competition_id=comp_id,
                        pipeline_id=pipeline_id
                    )

                    hard_gate_meta_by_pipeline[pipeline_id].append({
                        "insight_id": insight["Insight_ID"],
                        "hard_gate": hard_meta
                    })

                    if hard_decision == "drop":
                        gate_summary["hard_dropped"] += 1
                        continue

                    gate_summary["hard_kept"] += 1
                    hard_kept_candidates.append({
                        "competition_id": comp_id,
                        "pipeline_id": pipeline_id,
                        "insight": insight
                    })

            # 如果该competition在hard gate后已无可用insight，直接跳过
            if not hard_kept_candidates:
                continue

            # -----------------------------------
            # Step 3. Soft Gate（competition级 batch）
            # -----------------------------------
            soft_gate_results = self._soft_gate_batch_insights_for_competition(  # 通过hard的insight继续soft
                candidates=hard_kept_candidates,
                gate_context=gate_context,
                competition_id=comp_id
            )
            # soft_gate_results: insight_id -> meta

            # -----------------------------------
            # Step 4. 重组结果回原结构
            # -----------------------------------
            kept_pipelines = []

            for pipeline in pipelines:
                pipeline_id = pipeline.get("pipeline_id", "")
                insights = pipeline.get("insights", [])

                kept_insights = []
                gate_meta = []

                # 先加入 Hard Gate 的元数据。
                existing_hard_meta = hard_gate_meta_by_pipeline.get(pipeline_id, [])
                hard_meta_map = {m["insight_id"]: m for m in existing_hard_meta}

                for insight in insights:
                    insight_id = insight["Insight_ID"]
                    hard_meta_entry = hard_meta_map.get(insight_id)

                    # 没有hard meta一般不应发生，但防御性处理
                    if hard_meta_entry is None:
                        continue

                    # Hard Gate 已丢弃的条目只保留审核记录。
                    hard_decision = hard_meta_entry["hard_gate"].get("decision")
                    if hard_decision == "drop": # hard drop则跳过soft
                        gate_meta.append(hard_meta_entry)
                        continue

                    # hard通过后查soft结果
                    candidate_id = f"{pipeline_id}::{insight_id}"
                    soft_meta = soft_gate_results.get(candidate_id)
                    if soft_meta is None:
                        # LLM 未返回该条目时，保守地丢弃。
                        fallback_soft_meta = self._build_gate_meta(
                            competition_id=comp_id,
                            pipeline_id=pipeline_id,
                            insight_id=insight_id,
                            decision="drop",
                            stage="soft",
                            reasons=["Soft gate did not return a result for this insight; dropped conservatively."],
                            risk_tags=["soft_gate_missing_result"],
                            insight=insight
                        )
                        gate_meta.append({
                            "insight_id": insight_id,
                            "hard_gate": hard_meta_entry["hard_gate"],
                            "soft_gate": fallback_soft_meta
                        })
                        gate_summary["soft_drop"] += 1
                        continue

                    gate_meta.append({
                        "insight_id": insight_id,
                        "hard_gate": hard_meta_entry["hard_gate"],
                        "soft_gate": soft_meta
                    })

                    soft_decision = soft_meta.get("decision", "drop")
                    if soft_decision == "keep":
                        kept_insights.append(insight)
                        gate_summary["soft_keep"] += 1
                        gate_summary["final_kept"] += 1
                    elif soft_decision == "warn":
                        kept_insights.append(insight)
                        gate_summary["soft_warn"] += 1
                        gate_summary["final_kept"] += 1
                    else:
                        gate_summary["soft_drop"] += 1

                if kept_insights:  # pipeline业过gate的insights
                    # 叉：按confidence排序
                    kept_insights = self._sort_insights_by_soft_gate_confidence(
                        kept_insights=kept_insights,
                        gate_meta=gate_meta
                    )

                    kept_pipelines.append({
                        "pipeline_id": pipeline_id,
                        "insights": kept_insights,
                        "gate_meta": gate_meta
                    })

            if kept_pipelines:
                gated_result[comp_id] = {
                    "competition_info": competition_info,
                    "pipelines": kept_pipelines
                }

        gated_result["_gate_summary"] = gate_summary

        if gate_summary["final_kept"] == 0:
            return {
                "message": f"All candidate insights were filtered out by Hybrid Gate for phase: {current_phase}",
                "_gate_summary": gate_summary
            }

        # logger.info(f"Hybrid gate finished: {gate_summary}")
        return gated_result

    def _sort_insights_by_soft_gate_confidence(
            self,
            kept_insights: List[Dict[str, Any]],
            gate_meta: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        根据soft gate confidence对保留insights排序。
        keep/warn都可能保留，这里只按soft confidence降序。
        """
        confidence_map = {}
        for item in gate_meta:
            insight_id = item.get("insight_id")
            soft_gate = item.get("soft_gate", {})
            confidence = soft_gate.get("confidence", 0.0)
            try:
                confidence = float(confidence)
            except Exception:
                confidence = 0.0
            confidence_map[insight_id] = confidence

        return sorted(
            kept_insights,
            key=lambda x: confidence_map.get(x["Insight_ID"], 0.0),
            reverse=True
        )


    def _prefilter_insights_by_phase(self, comp_insights: Dict[str, Any], current_phase: str) -> Dict[str, Any]:
        """
        只保留当前阶段对应的insights。
        这是cheap prune，不是完整Gate。
        """
        if not comp_insights or "message" in comp_insights:
            return comp_insights

        if current_phase not in self.PHASE_MAPPING:
            return {"message": f"No SACKKnowledgeBase insights available for phase: {current_phase}"}

        target_phase = self.PHASE_MAPPING[current_phase].strip().lower()
        filtered = {}

        for comp_id, comp_data in comp_insights.items():
            filtered_pipelines = []

            for pipeline in comp_data.get("pipelines", []):
                filtered_insights = []
                for insight in pipeline.get("insights", []):
                    insight_phase = str(insight.get("Phase", "")).strip().lower()
                    if insight_phase == target_phase:
                        filtered_insights.append(insight)

                if filtered_insights:
                    filtered_pipelines.append({
                        "pipeline_id": pipeline.get("pipeline_id", ""),
                        "insights": filtered_insights
                    })

            if filtered_pipelines:
                filtered[comp_id] = {
                    "competition_info": comp_data.get("competition_info", {}),
                    "pipelines": filtered_pipelines
                }

        return filtered if filtered else {"message": f"No {current_phase} insights found in SACKKnowledgeBase"}

    def get_current_competition_edainsight(self,state) -> Dict[str, Dict[str, Dict[str, Any]]]:
        """
        绠€鍖栧悗锛氳繑鍥炵粨鏋勪负 {eda_type: {module: {field_path: value}}}
        去掉flat/df，只保留核心的嵌套字典
        """
        FIELD_WEIGHTS = {
            # pre_eda.data_quality
            "data_quality": {
                "missingness.overall_missing_rate": 0.15,
                "missingness.column_missing_distribution.proportions": 0.075,
                "missingness.row_completeness.complete_rows_ratio": 0.025,
                "missingness.row_completeness.rows_with_any_missing_ratio": 0.025,
                "missingness.row_completeness.high_missing_rows_ratio": 0.025,
                "missingness.missing_pattern_type.pattern_type": 0.1,
                "missingness.missing_pattern_type.confidence": 0.025,
                "outliers.outlier_columns_ratio": 0.15,
                "outliers.avg_outlier_ratio": 0.125,
                "outliers.outlier_severity_distribution": 0.1,
                "data_integrity.type_violation_ratio": 0.1,
                "data_integrity.unique_violation_ratio": 0.075
            },
            # pre_eda.basic_distribution
            "basic_distribution": {
                "numerical.skewness_profile.highly_skewed_ratio": 0.1,
                "numerical.skewness_profile.positive_skew_ratio": 0.08,
                "numerical.skewness_profile.negative_skew_ratio": 0.08,
                "numerical.skewness_profile.symmetric_ratio": 0.08,
                "numerical.scale_characteristics.wide_range_ratio": 0.05,
                "numerical.scale_characteristics.unit_heterogeneity": 0.03,
                "numerical.normality_assessment.normal_like_ratio": 0.08,
                "numerical.normality_assessment.tested_columns_count": 0.03,
                "numerical.multimodal_assessment.multimodal_ratio": 0.08,
                "numerical.multimodal_assessment.tested_columns_count": 0.03,
                "categorical.cardinality_pattern.low_cardinality_ratio": 0.05,
                "categorical.cardinality_pattern.medium_cardinality_ratio": 0.05,
                "categorical.cardinality_pattern.high_cardinality_ratio": 0.05,
                "categorical.cardinality_pattern.cardinality_distribution_type": 0.03,
                "categorical.cardinality_pattern.long_tail_prevalence": 0.03,
                "categorical.imbalance_profile.balanced_ratio": 0.03,
                "categorical.imbalance_profile.moderately_imbalanced_ratio": 0.03,
                "categorical.imbalance_profile.highly_imbalanced_ratio": 0.03,
                "categorical.rare_categories.columns_with_rare_categories_ratio": 0.03,
                "categorical.rare_categories.average_rare_category_density": 0.03
            },
            "basic_dimensionality": {
                "samples_per_feature": 1.0
            },
            # 此处省略 deep_eda.feature_relationships 的部分原有内容。
            "feature_relationships": {
                "correlation_structure.correlation_strength.weak_correlation_ratio": 0.08,
                "correlation_structure.correlation_strength.moderate_correlation_ratio": 0.08,
                "correlation_structure.correlation_strength.strong_correlation_ratio": 0.08,
                "correlation_structure.correlation_clustering.cluster_count": 0.05,
                "correlation_structure.correlation_clustering.largest_cluster_proportion": 0.05,
                "correlation_structure.multicollinearity.high_multicollinearity_ratio": 0.08,
                "correlation_structure.multicollinearity.redundant_pair_ratio": 0.08,
                "target_relationship.feature_importance_distribution.high_importance_ratio": 0.1,
                "target_relationship.feature_importance_distribution.importance_concentration_gini": 0.1,
                "target_relationship.interaction_with_target.complex_interaction_ratio": 0.06,
                "interaction_patterns.synergistic_interactions.synergistic_interaction_ratio": 0.05,
                "interaction_patterns.synergistic_interactions.interaction_type_distribution": 0.05,
                "interaction_patterns.categorical_numerical_interaction": 0.04,
                "interaction_patterns.conditional_dependencies.has_conditional_dependencies": 0.03,
                "interaction_patterns.conditional_dependencies.conditional_dependency_strength": 0.03,
                "interaction_patterns.nonlinear_relationships.nonlinear_ratio": 0.04
            },
            "complexity": {
                "dimensionality.samples_per_feature": 0.2,
                "dimensionality.feature_interaction_potential": 0.2,
                "sparsity_patterns.zero_dominated_ratio": 0.15,
                "sparsity_patterns.sparse_columns_ratio": 0.15,
                "noise_level.signal_to_noise_estimate": 0.15,
                "noise_level.inherent_uncertainty": 0.15
            },
            "special_scenarios": {
                "temporal_properties.is_time_series": 0.15,
                "temporal_properties.stationarity_strength": 0.15,
                "temporal_properties.periodicity_strength": 0.15,
                "causal_properties.confounder_strength": 0.15,
                "spatial_properties.spatial_correlation_strength": 0.15,
                "high_cardinality_impact.high_cardinality_ratio": 0.15,
                "high_cardinality_impact.high_cardinality_impact": 0.1
            }
        }

        comp_path = str(EDA_COMPETITION_DATA_DIR / state.competition)
        eda_paths = {
            "pre_eda": os.path.join(comp_path, "pre_insight_extraction/eda_insight.json"),
            "deep_eda": os.path.join(comp_path, "deep_insight_extraction/eda_insight.json")
        }
        eda_insight = {}  # 最终结构：eda_type → module → field_path → value

        for eda_type, eda_file_path in eda_paths.items():
            eda_insight[eda_type] = {}  # 初始化模块字典。
            if os.path.exists(eda_file_path) and os.path.getsize(eda_file_path) > 0:
                try:
                    # 读取原始嵌套 JSON。
                    with open(eda_file_path, 'r', encoding='utf-8') as f:
                        raw_json = json.load(f)

                    # 2. 直接组织为module→field_path→value（关键：不再扁平化，而是按FIELD_WEIGHTS匹配字段路径）
                    for module in MODULE_WEIGHTS.get(eda_type, {}).keys():
                        if module not in raw_json:
                            continue  # 跳过不存在的模块
                        module_data = raw_json[module]

                        # 递归提取字段路径（内部逻辑，不再暴露flat字典）
                        def extract_field_paths(nested_dict: Dict, parent_key: str = "", sep: str = ".") -> Dict[
                            str, Any]:
                            items = {}
                            for k, v in nested_dict.items():
                                new_key = f"{parent_key}{sep}{k}" if parent_key else k
                                if isinstance(v, dict):
                                    items.update(extract_field_paths(v, new_key, sep))
                                else:
                                    items[new_key] = v
                            return items

                        # 提取当前模块的所有字段路径→值
                        field_paths = extract_field_paths(module_data)
                        # 仅保留 FIELD_WEIGHTS 定义的字段。
                        valid_field_paths = {fp: val for fp, val in field_paths.items() if
                                             fp in FIELD_WEIGHTS.get(module, {})}
                        eda_insight[eda_type][module] = valid_field_paths

                except Exception as e:
                    print(f"Warning: Failed to get {eda_type} EDA for current competition: {e}")
                    continue
            else:
                print(f"Warning: {eda_type} file {eda_file_path} does not exist or is empty")

        return eda_insight




    def _build_gate_context_from_state(self, state: State) -> Dict[str, Any]:
        """
        尽量鲁棒地从state提取Gate上下文。
        """
        phase = state.phase
        background_info = state.background_info
        state_info = state.get_state_info()
        phase_context = state.context
        full_eda_insight = self.get_current_competition_edainsight(state)
        visible_eda_insight = self._get_phase_visible_eda_insight(full_eda_insight, phase)
        eda_summary = self._summarize_visible_eda_insight(visible_eda_insight, state)

        combined_text = "\n".join([
            f"PHASE: {phase}",
            f"BACKGROUND: {background_info}",
            f"STATE_INFO: {state_info}",
            f"PHASE_CONTEXT: {phase_context}",
            f"EDA_SUMMARY: {eda_summary}"
        ]).lower()

        context = {
            "phase": phase,
            "background_info": background_info,
            "state_info": state_info,
            "phase_context": phase_context,

            "full_eda_insight": full_eda_insight,
            "visible_eda_insight": visible_eda_insight,
            "eda_summary": eda_summary,

            "combined_text": combined_text,

            # very small set of explicit task signals
            "is_time_series": self._infer_is_time_series(
                visible_eda_insight=visible_eda_insight,
                fallback_text=combined_text
            ),
            "requires_group_cv": self._has_any_keyword(combined_text, [
                "groupkfold", "group k fold", "group-aware", "group split", "group cv", "group_id"
            ]),
            "has_missing_signal": self._infer_has_missing_signal(
                visible_eda_insight=visible_eda_insight,
                fallback_text=combined_text,
                missing_rate_threshold=0.0
            ),
            "phase_forbids_data_modification": phase.strip().lower() in [
                "preliminary exploratory data analysis",
                "in-depth exploratory data analysis"
            ]
        }
        return context



    def _get_phase_visible_eda_insight(self, full_eda_insight: Dict[str, Any], phase: str) -> Dict[str, Any]:
        """
        按阶段逐步披露EDAInsight，而不是始终传全量。
        规则：
        - Preliminary EDA: 只看 pre_eda 的浅层模块
        - Data Cleaning: 重点看 data_quality + 少量分布/维度信息
        - In-depth EDA: 看全部 pre_eda + deep_eda 的 feature_relationships / complexity / special_scenarios
        - Feature Engineering: 看 pre_eda 全部 + deep_eda 全部
        - Model Building...: 基本可查看全部信息
        """
        phase = (phase or "").strip()

        visible = {
            "pre_eda": {},
            "deep_eda": {}
        }

        pre_eda = full_eda_insight.get("pre_eda", {}) or {}
        deep_eda = full_eda_insight.get("deep_eda", {}) or {}

        if phase == "Preliminary Exploratory Data Analysis":
            for module in ["data_quality", "basic_distribution", "basic_dimensionality"]:
                if module in pre_eda:
                    visible["pre_eda"][module] = pre_eda[module]

        elif phase == "Data Cleaning":
            # 清洗阶段主要关注质量问题，辅以少量分布信息。
            for module in ["data_quality", "basic_distribution", "basic_dimensionality"]:
                if module in pre_eda:
                    visible["pre_eda"][module] = pre_eda[module]

        elif phase == "In-depth Exploratory Data Analysis":
            # 清洗阶段以质量问题为主，只补少量有助于判断处理策略的分布信息
            visible["pre_eda"] = pre_eda
            for module in ["feature_relationships", "complexity", "special_scenarios"]:
                if module in deep_eda:
                    visible["deep_eda"][module] = deep_eda[module]

        elif phase == "Feature Engineering":
            visible["pre_eda"] = pre_eda
            visible["deep_eda"] = deep_eda

        elif phase == "Model Building, Validation, and Prediction":
            visible["pre_eda"] = pre_eda
            visible["deep_eda"] = deep_eda

        else:
            # 默认保守处理：只提供 pre_eda 信息。
            visible["pre_eda"] = pre_eda

        return visible

    def _infer_is_time_series(self, visible_eda_insight: Dict[str, Any], fallback_text: str = "") -> bool:
        """
        优先从结构化EDAInsight判断是否时序任务；
        如果结构化信息缺失，再回退到文本关键词。
        """
        try:
            special_scenarios = (
                visible_eda_insight.get("deep_eda", {})
                .get("special_scenarios", {})
            )

            value = special_scenarios.get("temporal_properties.is_time_series", None)

            if isinstance(value, bool):
                return value

            # 数值类型：非零视为 True。
            if isinstance(value, (int, float)):
                return bool(value)

            # 字符串类型。
            if isinstance(value, str):
                v = value.strip().lower()
                if v in {"true", "1", "yes"}:
                    return True
                if v in {"false", "0", "no"}:
                    return False

        except Exception as e:
            logger.warning(f"Failed to infer is_time_series from visible_eda_insight: {e}")

        # 只有结构化字段未给出明确结论时才使用关键词回退判断。
        return self._has_any_keyword(fallback_text, [
            "time series", "temporal", "timestamp", "datetime", "鏃跺簭", "鏃堕棿搴忓垪"
        ])

    def _infer_has_missing_signal(
            self,
            visible_eda_insight: Dict[str, Any],
            fallback_text: str = "",
            missing_rate_threshold: float = 0.0
    ) -> bool:
        """
        优先从结构化 EDAInsight 判断当前是否存在缺失值信号；
        如果结构化信息缺失，再回退到文本关键词。
        """
        try:
            data_quality = (
                visible_eda_insight.get("pre_eda", {})
                .get("data_quality", {})
            )

            overall_missing_rate = data_quality.get("missingness.overall_missing_rate", None)

            if overall_missing_rate is not None:
                try:
                    overall_missing_rate = float(overall_missing_rate)
                    return overall_missing_rate > missing_rate_threshold
                except Exception:
                    pass


        except Exception as e:
            logger.warning(f"Failed to infer missing signal from visible_eda_insight: {e}")

        # 只有结构化字段缺失时才使用关键词回退判断。
        return self._has_any_keyword(fallback_text, [
            "missing", "null", "nan", "缂哄け"
        ])

    def _safe_filename(self, text: str) -> str:
        text = str(text).strip().replace(" ", "_")
        text = re.sub(r"[^A-Za-z0-9_\-\.]", "_", text)
        return text

    def _summarize_visible_eda_insight(self, visible_eda_insight: Dict[str, Any],state) -> str:
        """
        用 LLM 概括当前阶段可见的 EDAInsight，
        供Soft Gate使用。
        """
        cache_dir = os.path.join(state.restore_dir, "cache")
        os.makedirs(cache_dir, exist_ok=True)

        safe_phase = self._safe_filename(state.phase)
        cache_path = os.path.join(cache_dir, f"eda_gate_summary_{safe_phase}.txt")

        # 1. 优先读缓存
        if os.path.exists(cache_path) and os.path.getsize(cache_path) > 0:
            try:
                with open(cache_path, "r", encoding="utf-8") as f:
                    cached_summary = f.read().strip()
                if cached_summary:
                    logger.info(f"Loaded cached EDA gate summary from {cache_path}")
                    return cached_summary
            except Exception as e:
                logger.warning(f"Failed to read cached EDA summary: {e}")


        prompt = f"""
    You are summarizing phase-visible EDA insights for a downstream semantic gating module.

    Your task:
    Given the current phase and the phase-visible EDA insight JSON, produce a concise summary of ONLY the most decision-relevant signals for determining whether a historical CoreInsight is applicable.

    Requirements:
    1. Focus on signals relevant to the current phase.
    2. Keep the summary concise and factual.
    3. Mention only signals that may affect insight applicability, such as:
       - missing-value severity/pattern
       - outlier severity
       - skewness / multimodality
       - high-cardinality / rare categories / imbalance
       - dimensionality pressure
       - multicollinearity / redundancy
       - nonlinear relationships / interaction potential
       - time-series / special scenario indicators
    4. Do NOT recommend actions.
    5. Output plain text only.

    Current Phase:
    {state.phase}

    Phase-visible EDA Insight JSON:
    {json.dumps(visible_eda_insight, ensure_ascii=False, indent=2)}
    """.strip()

        try:
            resp, _ = self.llm.generate(prompt, [],max_completion_tokens=4096, enable_thinking=False)
            summary = resp.strip()

            # 3. 写缓存
            try:
                with open(cache_path, "w", encoding="utf-8") as f:
                    f.write(summary)
                logger.info(f"Saved EDA gate summary cache to {cache_path}")
            except Exception as e:
                logger.warning(f"Failed to save EDA summary cache: {e}")

            return summary
        except Exception as e:
            logger.warning(f"LLM EDA summarization failed: {e}")
            return f"No EDA summary available due to summarization failure: {str(e)}"

    def _hard_gate_single_insight(  # rule_based gate
            self,
            insight: Dict[str, Any],
            gate_context: Dict[str, Any],
            competition_id: str,
            pipeline_id: str
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Hard Gate只做明显错误拦截，不做复杂适用性分析。
        decision: keep / drop
        """
        insight_id = insight["Insight_ID"]
        insight_text = insight["Description"]

        reasons = []
        risk_tags = []

        # Rule 1: 当前EDA阶段，insight明确要求改数据/改特征 => drop
        if gate_context.get("phase_forbids_data_modification", False):
            if self._is_methodology_or_framework_description(insight_text):
                reasons.append(
                    "This insight describes an analysis framework/methodology rather than explicit data modification."
                )
            elif self._contains_explicit_data_modification_for_eda_phase(insight_text):
                reasons.append(
                    "EDA phase should not modify data/features, but this insight explicitly suggests modification."
                )
                risk_tags.append("phase_constraint_conflict")
                return "drop", self._build_gate_meta(
                    competition_id, pipeline_id, insight_id, "drop", "hard",
                    reasons, risk_tags, insight
                )

        # 当前为时间序列任务时，丢弃建议随机划分的经验。
        if gate_context.get("is_time_series", False):
            if self._has_any_keyword(insight_text, [
                "random split", "shuffle split", "kfold", "stratifiedkfold"
            ]) and not self._has_any_keyword(insight_text, [
                "time series split", "rolling", "temporal validation"
            ]):
                reasons.append("Current task appears to be time-series, but this insight suggests random CV/split.")
                risk_tags.append("protocol_conflict")
                return "drop", self._build_gate_meta(
                    competition_id, pipeline_id, insight_id, "drop", "hard",
                    reasons, risk_tags, insight
                )

        # 当前要求分组验证时，丢弃建议普通随机划分的经验。
        if gate_context.get("requires_group_cv", False):
            if self._has_any_keyword(insight_text, [
                "random split", "kfold", "stratifiedkfold"
            ]) and not self._has_any_keyword(insight_text, [
                "groupkfold", "group k fold", "group-aware"
            ]):
                reasons.append(
                    "Current task appears to require group-aware validation, but this insight suggests non-group split.")
                risk_tags.append("protocol_conflict")
                return "drop", self._build_gate_meta(
                    competition_id, pipeline_id, insight_id, "drop", "hard",
                    reasons, risk_tags, insight
                )

        reasons.append("Passed hard gate.")
        return "keep", self._build_gate_meta(
            competition_id, pipeline_id, insight_id, "keep", "hard",
            reasons, risk_tags, insight
        )

    def _contains_explicit_data_modification_for_eda_phase(self, text: str) -> bool:
        """
        只识别明确建议修改数据或特征的表述。
        避免把 'standardized analysis pipeline' 这类流程描述误判成数据标准化操作。
        """
        if not text:
            return False

        text = str(text).lower().strip()

        patterns = [
            # 删除列/特征
            r"\bdrop\s+(the\s+)?(column|columns|feature|features)\b",
            r"\bremove\s+(the\s+)?(column|columns|feature|features)\b",
            r"\bdelete\s+(the\s+)?(column|columns|feature|features)\b",

            # 缺失值处理
            r"\bimput(e|ation|ing)\b",
            r"\bfill\s+(the\s+)?missing\b",
            r"\bfill\s+missing\s+values\b",
            r"\bfillna\b",
            r"\breplace\s+missing\s+values\b",

            # 编码
            r"\btarget\s+encoding\b",
            r"\btarget\s+encode\b",
            r"\bone[\-\s]?hot\s+encoding\b",
            r"\bone[\-\s]?hot\s+encode\b",
            r"\blabel\s+encoding\b",
            r"\blabel\s+encode\b",
            r"\bordinal\s+encoding\b",
            r"\bordinal\s+encode\b",

            # 编码
            r"\bstandardiz(e|ed|ing|ation)\s+(the\s+)?(data|dataset|column|columns|feature|features|variable|variables|input|inputs)\b",
            r"\bnormaliz(e|ed|ing|ation)\s+(the\s+)?(data|dataset|column|columns|feature|features|variable|variables|input|inputs)\b",
            r"\bscal(e|ed|ing)\s+(the\s+)?(data|dataset|column|columns|feature|features|variable|variables|input|inputs)\b",

            # 名词化的描述也可能明确指向数据处理动作。
            r"\b(feature|features|data|dataset|columns?|variables?|inputs?)\s+(were\s+|was\s+)?standardiz(ed|ation)\b",
            r"\b(feature|features|data|dataset|columns?|variables?|inputs?)\s+(were\s+|was\s+)?normaliz(ed|ation)\b",
            r"\b(feature|features|data|dataset|columns?|variables?|inputs?)\s+(were\s+|was\s+)?scal(ed|ing)\b",

            # 特征构造
            r"\bconstruct\s+(a\s+|new\s+|additional\s+)?feature\b",
            r"\bconstruct\s+features\b",
            r"\bcreate\s+(a\s+|new\s+|additional\s+)?feature\b",
            r"\bcreate\s+features\b",
            r"\bengineer\s+(a\s+|new\s+|additional\s+)?feature\b",
            r"\bengineer\s+features\b",
            r"\bfeature\s+construction\b",
        ]

        return any(re.search(pattern, text) for pattern in patterns)

    def _is_methodology_or_framework_description(self, text: str) -> bool:
        """
        判断这段话是否描述分析框架、方法或流程规范，
        而非建议直接修改数据。
        """
        if not text:
            return False

        text = str(text).lower().strip()

        safe_patterns = [
            r"\bstandardized?\s+analysis\s+pipeline\b",
            r"\bstandardized?\s+workflow\b",
            r"\bstandardized?\s+eda\s+(framework|process|procedure)\b",
            r"\bsystematic\s+eda\s+(framework|process|workflow)\b",
            r"\banalysis\s+framework\b",
            r"\bevaluation\s+framework\b",
            r"\bcomprehensive\s+data\s+understanding\b",
            r"\bframework\s+implementation\b",
        ]

        return any(re.search(pattern, text) for pattern in safe_patterns)
        
    def _soft_gate_batch_insights_for_competition(
            self,
            candidates: List[Dict[str, Any]],
            gate_context: Dict[str, Any],
            competition_id: str
    ) -> Dict[str, Dict[str, Any]]:
        """
        对同一个 competition 下通过 hard gate 的所有 insights 做批量 soft gate。

        输入 candidates 的结构：
        [
            {
                "competition_id": ...,
                "pipeline_id": ...,
                "insight": {...}
            },
            ...
        ]

        返回：
        {
            candidate_id: soft_gate_meta,
            ...
        }

        其中 candidate_id = "{pipeline_id}::{insight_id}"
        在竞赛级批处理中唯一标识一条候选经验。
        """
        if not candidates:
            return {}

        prompt = self._build_soft_gate_batch_prompt_for_competition(
            candidates=candidates,
            gate_context=gate_context,
            competition_id=competition_id
        )

        try:
            llm_raw, _ = self.llm.generate(prompt, [],max_completion_tokens=4096)
        except Exception as e:
            logger.warning(f"Soft gate LLM call failed: {e}")
            llm_raw = "[]"

        parsed_items = self._parse_soft_gate_batch_output(llm_raw)

        # 建立原始 candidate 映射，便于补全 meta
        candidate_map: Dict[str, Dict[str, Any]] = {}
        for item in candidates:
            insight = item["insight"]
            pipeline_id = item["pipeline_id"]
            insight_id = insight["Insight_ID"]
            candidate_id = f"{pipeline_id}::{insight_id}"
            candidate_map[candidate_id] = item

        results: Dict[str, Dict[str, Any]] = {}

        # 先处理 LLM 返回的结果
        for parsed in parsed_items:
            candidate_id = str(parsed.get("candidate_id", "")).strip()
            if not candidate_id:
                continue
            if candidate_id not in candidate_map:
                continue

            candidate = candidate_map[candidate_id]
            insight = candidate["insight"]
            pipeline_id = candidate["pipeline_id"]
            insight_id = insight["Insight_ID"]

            decision = parsed.get("decision", "warn")
            if decision not in {"keep", "warn", "drop"}:
                decision = "warn"

            confidence = parsed.get("confidence", None)
            try:
                if confidence is not None:
                    confidence = float(confidence)
            except Exception:
                confidence = None

            risk_tags = parsed.get("risk_tags", [])
            if not isinstance(risk_tags, list):
                risk_tags = [str(risk_tags)]

            meta = self._build_gate_meta(
                competition_id=competition_id,
                pipeline_id=pipeline_id,
                insight_id=insight_id,
                decision=decision,
                stage="soft",
                reasons=[parsed.get("reason", "No reason returned by LLM batch soft gate.")],
                risk_tags=risk_tags,
                insight=insight,
                confidence=confidence,
                adaptation_hint=parsed.get("adaptation_hint")
            )
            meta["candidate_id"] = candidate_id
            results[candidate_id] = meta

        # 对 LLM 漏判的结果做保守回填
        for candidate_id, candidate in candidate_map.items():
            if candidate_id not in results:
                insight = candidate["insight"]
                pipeline_id = candidate["pipeline_id"]
                insight_id = insight["Insight_ID"]

                meta = self._build_gate_meta(
                    competition_id=competition_id,
                    pipeline_id=pipeline_id,
                    insight_id=insight_id,
                    decision="drop",
                    stage="soft",
                    reasons=["Soft gate batch did not return this insight; dropped conservatively."],
                    risk_tags=["soft_gate_missing_result"],
                    insight=insight
                )
                meta["candidate_id"] = candidate_id
                results[candidate_id] = meta

        return results

    def _build_soft_gate_batch_prompt_for_competition(
            self,
            candidates: List[Dict[str, Any]],
            gate_context: Dict[str, Any],
            competition_id: str
    ) -> str:
        """
        competition绾у埆鎵归噺soft gate prompt
        """
        candidate_payload = []
        for item in candidates:
            insight = item["insight"]
            pipeline_id = item["pipeline_id"]
            insight_id = insight["Insight_ID"]
            candidate_id = f"{pipeline_id}::{insight_id}"

            candidate_payload.append({
                "candidate_id": candidate_id,
                "pipeline_id": pipeline_id,
                "insight_id": insight_id,
                "flattened_insight_text": insight.get("Description", ""),
                "effectiveness": insight.get("Effectiveness", "")
            })

        return f"""
    You are a semantic gate for selecting whether historical CoreInsights should be included as candidate references for the current data-science task.

    Your goal is ONLY to judge whether each candidate CoreInsight is worth passing to the Planner.

    You are given multiple candidate CoreInsights from the same historical competition.
    Evaluate EACH candidate independently, but you may compare them for relative usefulness, specificity, and redundancy.

    Please focus on:
    1. Is the insight applicable to the current task context?
    2. Is it supported or contradicted by the currently visible EDA signals?
    3. Is it too generic to be useful?
    4. Is it likely helpful as a candidate reference for the current phase?
    5. If it is only partially applicable, return "warn" instead of "drop".

    Current Phase Context:
    {gate_context.get("phase_context", "")}

    Current Phase:
    {gate_context.get("phase", "")}

    Current Task Context:
    [Background]
    {gate_context.get("background_info", "")}

    [State Info]
    {gate_context.get("state_info", "")}

    [Phase-visible EDA Signals]
    {gate_context.get("eda_summary", "")}

    Historical Competition ID:
    {competition_id}

    Candidate CoreInsights:
    {json.dumps(candidate_payload, ensure_ascii=False, indent=2)}

    Output requirements:
    Return ONLY valid JSON as a list, one item for each candidate insight.
    Schema:
    [
      {{
        "candidate_id": "<pipeline_id>::<insight_id>",
        "decision": "keep" | "warn" | "drop",
        "confidence": 0.0,
        "reason": "one concise sentence",
        "risk_tags": ["tag1", "tag2"],
        "adaptation_hint": "one concise sentence"
      }}
    ]

    Decision guideline:
    - keep: clearly useful and reasonably applicable under the current phase and visible EDA signals
    - warn: partially applicable / needs adaptation / some uncertainty
    - drop: too generic, irrelevant, contradicted by current visible EDA signals, redundant, or unlikely helpful for current task

    Important:
    - Evaluate EVERY candidate insight and return one result for each candidate_id.
    - Use only the currently visible phase-specific EDA signals.
    - Do not assume unavailable deeper-stage information.
    - Do not omit any candidate_id.

    Do not output anything except JSON.
    """.strip()


    def _parse_soft_gate_batch_output(self, llm_raw: str) -> List[Dict[str, Any]]:
        """
        解析batch soft gate输出，期望是JSON list。
        """
        try:
            parsed = json.loads(llm_raw)
            if isinstance(parsed, list):
                return parsed
        except Exception:
            pass

        # 尝试提取JSON数组
        try:
            match = re.search(r"\[\s*\{.*\}\s*\]", llm_raw, re.DOTALL)
            if match:
                parsed = json.loads(match.group(0))
                if isinstance(parsed, list):
                    return parsed
        except Exception:
            pass

        logger.warning(f"Failed to parse batch soft gate output, raw={llm_raw}")
        return []

    def _build_gate_meta(
            self,
            competition_id: str,
            pipeline_id: str,
            insight_id: str,
            decision: str,
            stage: str,
            reasons: List[str],
            risk_tags: List[str],
            insight: Dict[str, Any],
            confidence: Optional[float] = None,
            adaptation_hint: Optional[str] = None
    ) -> Dict[str, Any]:
        meta = {
            "competition_id": competition_id,
            "pipeline_id": pipeline_id,
            "insight_id": insight_id,
            "decision": decision,
            "stage": stage,
            "reasons": reasons,
            "risk_tags": list(sorted(set(risk_tags))) if risk_tags else [],
            "phase": insight.get("Phase", ""),
            "insight_preview": insight["Description"][:300]
        }
        if confidence is not None:
            meta["confidence"] = confidence
        if adaptation_hint is not None:
            meta["adaptation_hint"] = adaptation_hint
        return meta


    def _has_any_keyword(self, text: str, keywords: List[str]) -> bool:
        if not text:
            return False
        text = text.lower()
        return any(k.lower() in text for k in keywords)

        
    def get_similar_comp_coreinsight(self, state: State, retrieval_mode: str = "weighted_topk") -> Dict[str, Any]:
        """执行检索流程，返回整合后的案例信息"""
        # 1. 检索相似竞赛
        similar_comps = self.retrieve_similar_competitions(state, k=5, retrieval_mode=retrieval_mode)
        if self.last_retrieval_error:
            failed_result = {
                "message": "Knowledge retrieval failed",
                "error": self.last_retrieval_error,
                "_retrieval_status": "failed",
            }
            output_path = f'{state.restore_dir}/sack_core_insights.json'
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(failed_result, f, ensure_ascii=False, indent=4)
            logger.error("SACKKnowledgeBase retrieval failed; details saved to %s", output_path)
            return failed_result

        # 3. 整合结果
        core_insights = self.retrieve_core_insights(competitions=similar_comps, top_pipelines_per_comp=3)

        # 3. 整合结果
        comp_insights = self.integrate_insights(similar_comps,core_insights)


        # 4. Hybrid Gate
        gated_insights = self.gated_insights(comp_insights, state)
        logger.info(f"Gated insights summary: {gated_insights.get('_gate_summary', {}) if isinstance(gated_insights, dict) else {} }")

        # 5. 保存结果到本地（供Planner后续使用）
        output_path = f'{state.restore_dir}/sack_core_insights.json'
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(gated_insights, f, ensure_ascii=False, indent=4)
        logger.info(f"SACKKnowledgeBase gated core insights saved to {output_path}")

        return gated_insights

    def get_phase_insights_text(self, filtered_insights: Dict) -> str:
        """将当前阶段筛选后的核心经验格式化为提示词文本，并附上供 Planner 引用的 ID"""
        if filtered_insights and filtered_insights.get("_retrieval_status") == "failed":
            return (
                "Knowledge retrieval failed for the current phase. "
                f"Do not assume historical case knowledge is available. Error: {filtered_insights.get('error', 'unknown')}"
            )
        if not filtered_insights or ("message" in filtered_insights and "No" in filtered_insights["message"]):
            return "No relevant insights found for the current phase."

        header = (
            f"Below are core strategies (called 'insights') from similar data science competitions. "
            "These insights are extracted from high-performing solutions (called 'pipelines') that addressed similar competitions.\n"
            "- Each insight is associated with a unique ID (use these IDs when referencing).\n"
            "- Prioritize strategies with high effectiveness and relevance to the current task.\n"
        )

        insights_text = [header]
        # 按竞赛相似性排名排序
        valid_comp_ids = [
            comp_id for comp_id in filtered_insights.keys()
            if comp_id != "_gate_summary" and isinstance(filtered_insights[comp_id], dict)
               and "competition_info" in filtered_insights[comp_id]
        ]

        if not valid_comp_ids:
            return "No relevant insights found for the current phase."

        # 按竞赛相似性排名排序
        sorted_comp_ids = sorted(
            valid_comp_ids,
            key=lambda x: filtered_insights[x]["competition_info"]["rank"]
        )

        for comp_idx, comp_id in enumerate(sorted_comp_ids, 1):
            comp_data = filtered_insights[comp_id]
            comp_info = comp_data["competition_info"]

            # 如果有reader reply 尽可能提炼关键信息而不是直接用overview作为上下文
            comp_name = comp_id.split("/")[-1]
            comp_path = EDA_COMPETITION_DATA_DIR / comp_name
            comp_background_path = f"{comp_path}/understand_background/reader_reply.txt"

            if os.path.exists(comp_background_path):
                summary_cache_path = f"{comp_path}/understand_background/background_summary_cache.txt"

                # 1. 优先读缓存
                if os.path.exists(summary_cache_path) and os.path.getsize(summary_cache_path) > 0:
                    try:
                        with open(summary_cache_path, "r", encoding="utf-8") as f:
                            background = f.read().strip()
                        logger.info(f"Loaded cached background summary from {summary_cache_path}")
                    except Exception as e:
                        logger.warning(f"Failed to read cached background summary: {e}")
                        background = None
                else:
                    background = None

                # 2. 没缓存再读原文并总结
                if not background:
                    with open(comp_background_path, 'r', encoding='utf-8') as f:
                        raw_background = f.read()

                    try:
                        background, _ = self.llm.generate(
                            f"Summarize the complete background of the competition in one paragraph (250 words), and try not to omit any key information: \n{raw_background}",
                            [],
                            max_completion_tokens=4096,
                            enable_thinking=False
                        )
                        background = background.strip()

                        # 3. 写缓存
                        try:
                            with open(summary_cache_path, "w", encoding="utf-8") as f:
                                f.write(background)
                            logger.info(f"Saved background summary cache to {summary_cache_path}")
                        except Exception as e:
                            logger.warning(f"Failed to save background summary cache: {e}")

                    except Exception as e:
                        logger.warning(f"Failed to summarize competition background: {e}")
                        background = comp_info.get("overview", "")
            else:
                background = comp_info.get("overview", "")

            # 1. 竞赛层信息（含competition_id）
            comp_part = (
                f"### Similar Competition {comp_idx} ###\n"
                f"- ID (competition_id): {comp_name}\n"
                f"- Background: {background[:250]}...\n"  
                f"- Similarity Score: {comp_info['final_similarity']:.2f}\n"
            )

            # 2. Pipeline层信息（含pipeline_id）
            for pipe in comp_data["pipelines"]:
                pipeline_id = pipe["pipeline_id"]  # 从integrate_insights中解析的pipeline_id

                pipe_part = (
                    f"  - Pipeline ID (pipeline_id): {pipeline_id}\n"
                    f"    Insights in this pipeline:\n"
                )


                # 3. 见解层信息,包括gate_meta
                gate_meta_map = {}
                for meta in pipe.get("gate_meta", []):
                    insight_id = meta.get("insight_id")
                    if insight_id:
                        gate_meta_map[insight_id] = meta

                for insight in pipe.get("insights", []):
                    ins_id = insight["Insight_ID"]
                    description = insight.get("Description", "N/A")
                    effectiveness = str(insight.get("Effectiveness", "N/A"))

                    gate_status_text = ""
                    meta = gate_meta_map.get(ins_id, {})
                    soft_gate = meta.get("soft_gate", {})
                    if soft_gate:
                        decision = soft_gate.get("decision", "")
                        adaptation_hint = soft_gate.get("adaptation_hint", "")
                        reasons = soft_gate.get("reasons", [])

                        if decision == "warn":
                            gate_status_text += f"        Gate Status: warn\n"
                            if adaptation_hint:
                                gate_status_text += f"        Adaptation Hint: {adaptation_hint}\n"
                            elif reasons:
                                gate_status_text += f"        Gate Note: {reasons[0]}\n"
                        elif decision == "keep":
                            # Keep 的结果可简要标注，也可不写。
                            gate_status_text += f"        Gate Status: keep\n"

                    ins_part = (
                        f"      - Insight ID (Insight_ID): {ins_id}\n"
                        f"        Description: {description}\n"
                        f"        Effectiveness: {effectiveness[:100]}...\n"
                        f"{gate_status_text}"
                    )
                    pipe_part += ins_part

                comp_part += pipe_part + "\n"

            insights_text.append(f"{comp_part}\n---")

        return "\n".join(insights_text)

    def get_code_snippets_for_plan(self, plan: str) -> Dict:
        task_code_mapping = {}
        # 匹配 STEP X 到下一 STEP 或文本末尾，完整提取任务描述。
        task_pattern = r"### STEP (\d+)\s+Task: (.*?)(?=\s+### STEP|\Z)"
        # 用re.DOTALL让.匹配换行，re.MULTILINE适配多行
        tasks = re.findall(task_pattern, plan, re.DOTALL | re.MULTILINE)

        for step, task_desc in tasks:
            # 修复：匹配Referenced from: 到下一个空行/Task结束，完整提取所有Insight
            insight_pattern = r"Referenced from: (.*?)(?=\s+Tools, involved features|\Z)"
            insight_match = re.search(insight_pattern, task_desc, re.DOTALL)
            if not insight_match:
                # 没有 Insight 时也保留任务描述，避免步骤丢失。
                task_code_mapping[step] = {
                    "task_desc": task_desc.strip(),
                    "insights": []
                }
                continue

            # 拆分多个insight（按分号分隔）
            insights_str = insight_match.group(1).strip()
            individual_insights = [ins.strip() for ins in insights_str.split(';') if ins.strip()]

            # 初始化当前步骤的映射。
            task_code_mapping[step] = {
                "task_desc": task_desc.strip(),
                "insights": []
            }

            for ins in individual_insights:
                # 提取 Competition、Pipeline 和 Insight ID。
                ins_details = re.search(
                    r"Competition\[([^]]+)\] -> Pipeline\[([^]]+)\] -> Insight\[([^]]+)\]",
                    ins
                )
                if not ins_details:
                    logger.warning(f"Insight鏍煎紡閿欒锛屾棤娉曡В鏋愶細{ins}")
                    continue
                competition_id = ins_details.group(1)
                pipeline_id = ins_details.group(2)
                insight_id = ins_details.group(3)
                # 规范 URI 格式，去除多余空格。
                insight_uri = f"http://sack.local/resource/kaggle/{competition_id}/{pipeline_id}/insight/{insight_id}"

                # 检索代码段，异常时保留Insight信息（仅标记失败）
                try:
                    code_snippets = self.sack_knowledge.get_insight_code_snippet(insight_uri=insight_uri)
                except Exception as e:
                    logger.warning("Failed to retrieve insight %s: %s", insight_uri, e)
                    code_snippets = []  # 代码片段列表为空时，仍保留 Insight 条目。

                # 添加到当前任务的insights列表
                task_code_mapping[step]["insights"].append({
                    "source": ins,
                    "insight_uri": insight_uri,
                    "code_snippets": code_snippets
                })

        return task_code_mapping
