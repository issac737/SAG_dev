"""
数据库模块

提供SQLAlchemy ORM模型和数据库操作
"""

from dataflow.db.base import Base, get_engine, get_session_factory, init_database, close_database
from dataflow.db.models import (
    Article,
    ArticleSection,
    ChatConversation,
    ChatMessage,
    Entity,
    EntityType,
    EventEntity,
    ModelConfig,
    SourceChunk,
    SourceConfig,
    SourceEvent,
    Task,
)

__all__ = [
    # Base
    "Base",
    "get_engine",
    "get_session_factory",
    "init_database",
    "close_database",
    # Models
    "SourceConfig",
    "Article",
    "ArticleSection",
    "EntityType",
    "Entity",
    "EventEntity",
    "SourceEvent",
    "Task",
    "ChatConversation",
    "ChatMessage",
    "ModelConfig",
    "SourceChunk",
]
