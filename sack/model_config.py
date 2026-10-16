"""Environment-backed model choices, shared by Agents, tools and profiling."""

import os


DEFAULT_MODELS = {
    "general": "qwen-plus",
    "coder": "qwen3.7-plus",
    "vision": "qwen3.6-flash",
    "embedding": "text-embedding-v3",
    # The legacy knowledge embedding client has a separate vector contract.
    "knowledge_embedding": "Qwen3-Embedding-0.6B",
}

FALLBACK_ROLES = {
    "reader": "general",
    "planner": "general",
    "reviewer": "general",
    "summarizer": "general",
    "retriever": "general",
    "knowledge": "general",
    "developer": "coder",
    "debug": "coder",
    "test": "coder",
}


def get_model(role: str) -> str:
    """Resolve a role each time so environment overrides are not cached."""
    if role not in DEFAULT_MODELS and role not in FALLBACK_ROLES:
        raise ValueError(f"Unknown model role: {role}")
    key = f"SACK_MODEL_{role.upper()}"
    configured = os.environ.get(key)
    if configured is not None:
        if not configured.strip():
            raise ValueError(f"{key} must not be empty")
        return configured.strip()
    if role in FALLBACK_ROLES:
        return get_model(FALLBACK_ROLES[role])
    return DEFAULT_MODELS[role]


def infer_endpoint_role(model: str) -> str:
    """Retain model-only API calls; runtime call sites pass explicit roles.

    Role-based routing remains unambiguous even when several roles use the
    same model name but have different deployment endpoints.
    """
    if model in {get_model(role) for role in ("coder", "developer", "debug", "test")}:
        return "coder"
    if model == get_model("vision"):
        return "vision"
    if model in {"qwen3-coder-plus", "qwen3-coder-30b-a3b-instruct"}:
        return "coder"
    if model == "qwen3-vl-flash":
        return "vision"
    return "general"
