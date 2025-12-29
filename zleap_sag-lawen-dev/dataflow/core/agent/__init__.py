"""
Agent 模块

基于 JSON 系统提示词的智能数据处理 Agent 系统
"""

from dataflow.core.agent.base import BaseAgent
from dataflow.core.agent.builder import Builder
from dataflow.core.agent.researcher import ResearcherAgent
from dataflow.core.agent.summarizer import SummarizerAgent

__all__ = [
    "BaseAgent",
    "Builder",
    "ResearcherAgent",
    "SummarizerAgent",
]

__version__ = "2.0.0"
