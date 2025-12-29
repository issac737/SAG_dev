"""文档相关 Schema"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field

from dataflow.api.schemas.base import TimestampMixin


class DocumentUploadResponse(BaseModel):
    """文档上传响应"""

    filename: Optional[str] = None
    file_path: str
    article_id: Optional[str] = None
    task_id: Optional[str] = None
    success: bool = True
    message: Optional[str] = None


class DocumentUpdate(BaseModel):
    """文档更新请求"""

    title: Optional[str] = None
    summary: Optional[str] = None
    tags: Optional[List[str]] = None
    category: Optional[str] = None


class DocumentResponse(TimestampMixin):
    """文档响应"""

    id: str
    source_config_id: str
    title: str
    summary: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[List[str]] = None
    status: str  # PENDING, PROCESSING, COMPLETED, FAILED
    error: Optional[str] = None  # 错误信息
    extra_data: Optional[Dict[str, Any]] = None
    created_time: datetime
    updated_time: Optional[datetime] = None

    # 统计信息
    sections_count: int = 0
    events_count: int = 0

    class Config:
        from_attributes = True


class ArticleSectionResponse(BaseModel):
    """文章片段响应"""

    id: str
    article_id: str

    # 排序和类型
    order_index: int = 0
    type: Optional[str] = None
    rank: int

    # 标题和内容
    heading: Optional[str] = None
    content: str
    raw_content: Optional[str] = None

    # 图片和统计
    image_url: Optional[str] = None
    length: int = 0

    # 扩展和时间戳
    extra_data: Optional[Dict[str, Any]] = None
    created_time: datetime
    updated_time: Optional[datetime] = None

    class Config:
        from_attributes = True


class EntityInfo(BaseModel):
    """实体信息（包含在事项中的描述）"""

    id: str
    name: str
    type: str
    weight: float = 1.0
    description: Optional[str] = None  # 该实体在此事项中的具体描述/角色


class ChatMessageResponse(BaseModel):
    """聊天消息响应（用于事项的 references 字段）"""

    id: str
    conversation_id: str
    timestamp: datetime
    content: Optional[str] = None
    sender_id: Optional[str] = None
    sender_name: Optional[str] = None

    class Config:
        from_attributes = True


class SourceEventResponse(BaseModel):
    """事项响应"""

    id: str
    source_config_id: str
    source_type: str
    source_id: str
    article_id: Optional[str] = None  # 兼容前端（从 source_id 计算）
    conversation_id: Optional[str] = None  # 兼容前端
    title: str
    summary: str
    content: str
    category: Optional[str] = None  # 事项分类（技术、产品、市场、研究、管理等）
    rank: int
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    references: Optional[List[Union[ArticleSectionResponse, ChatMessageResponse]]] = []
    entities: Optional[List[EntityInfo]] = []
    extra_data: Optional[Dict[str, Any]] = None
    created_time: datetime
    updated_time: Optional[datetime] = None

    # 新增字段：来源和文档名称
    source_name: Optional[str] = ""  # 信息源名称（from SourceConfig.name）
    document_name: Optional[str] = ""  # 文档名称（from Article.title）

    class Config:
        from_attributes = True

    @classmethod
    def from_orm_with_entities(cls, event, references_dict: dict = None):
        """
        从ORM对象转换，包含实体信息和完整片段/消息信息

        Args:
            event: SourceEvent ORM 对象
            references_dict: 引用的片段/消息字典
                - 对于 ARTICLE 类型：{section_id: ArticleSection}
                - 对于 CHAT 类型：{message_id: ChatMessage}
        """
        entities = [
            EntityInfo(
                id=assoc.entity.id,
                name=assoc.entity.name,
                type=assoc.entity.type,
                weight=float(assoc.weight),
                description=assoc.description,  # 从 event_entity 关联表获取描述
            )
            for assoc in event.event_associations
        ]

        # 根据 source_type 和 references ID 查询完整引用信息
        reference_items = []
        if references_dict and event.references:
            for ref_id in event.references:
                if ref_id in references_dict:
                    ref_obj = references_dict[ref_id]

                    # 判断是 ArticleSection 还是 ChatMessage
                    if hasattr(ref_obj, 'article_id'):
                        # ArticleSection
                        reference_items.append(
                            ArticleSectionResponse(
                                id=ref_obj.id,
                                article_id=ref_obj.article_id,
                                rank=ref_obj.rank,
                                heading=ref_obj.heading,
                                content=ref_obj.content,
                                extra_data=ref_obj.extra_data,
                                created_time=ref_obj.created_time,
                                updated_time=ref_obj.updated_time,
                            )
                        )
                    elif hasattr(ref_obj, 'conversation_id'):
                        # ChatMessage
                        reference_items.append(
                            ChatMessageResponse(
                                id=ref_obj.id,
                                conversation_id=ref_obj.conversation_id,
                                timestamp=ref_obj.timestamp,
                                content=ref_obj.content,
                                sender_id=ref_obj.sender_id,
                                sender_name=ref_obj.sender_name,
                            )
                        )

        return cls(
            id=event.id,
            source_config_id=event.source_config_id,
            source_type=event.source_type,
            source_id=event.source_id,
            article_id=event.article_id,
            conversation_id=event.conversation_id,
            title=event.title,
            summary=event.summary,
            content=event.content,
            category=event.category,
            rank=event.rank,
            start_time=event.start_time,
            end_time=event.end_time,
            references=reference_items,
            entities=entities,
            extra_data=event.extra_data,
            created_time=event.created_time,
            updated_time=event.updated_time,
            # 从 event 对象读取动态添加的属性
            source_name=getattr(event, "source_name", ""),
            document_name=getattr(event, "document_name", ""),
        )
