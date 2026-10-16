"""SACK: Self-adaptive case-based knowledge for automated data science."""

from .env import load_project_env

load_project_env()

from .paths import PROJECT_ROOT

__all__ = ["PROJECT_ROOT"]
