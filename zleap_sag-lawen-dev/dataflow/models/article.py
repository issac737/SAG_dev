"""
文章数据模型
"""

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import Field

from dataflow.models.base import DataFlowBaseModel, MetadataMixin, TimestampMixin


class ArticleStatus(str, Enum):
    """文章状态"""

    PENDING = "PENDING"  # 待处理
    COMPLETED = "COMPLETED"  # 已完成
    FAILED = "FAILED"  # 失败


class Article(DataFlowBaseModel, MetadataMixin, TimestampMixin):
    """文章模型"""

    id: Optional[str] = Field(default=None, description="文章ID (UUID)")
    source_config_id: str = Field(..., description="信息源ID")
    title: str = Field(..., max_length=500, description="文章标题")
    summary: Optional[str] = Field(default=None, description="文章摘要（LLM生成）")
    content: Optional[str] = Field(default=None, description="文章正文")
    status: ArticleStatus = Field(
        default=ArticleStatus.PENDING, description="处理状态")
    category: Optional[str] = Field(
        default=None, max_length=50, description="分类")
    tags: Optional[List[str]] = Field(default=None, description="标签列表")

    def get_category(self) -> Optional[str]:
        """获取文章分类"""
        if self.extra_data and "category" in self.extra_data:
            return self.extra_data["category"]
        return self.category

    def get_tags(self) -> List[str]:
        """获取文章标签"""
        if self.tags:
            return self.tags
        if self.extra_data and "tags" in self.extra_data:
            return self.extra_data["tags"]
        return []

    def get_headings(self) -> List[str]:
        """获取文章标题列表"""
        if self.extra_data and "headings" in self.extra_data:
            return self.extra_data["headings"]
        return []


class ArticleSection(DataFlowBaseModel, MetadataMixin, TimestampMixin):
    """文章片段模型"""

    id: Optional[str] = Field(default=None, description="片段ID (UUID)")
    article_id: str = Field(..., description="文章ID")

    # 排序和类型
    order_index: int = Field(default=0, ge=0, description="排序索引")
    type: Optional[str] = Field(default="TEXT", description="片段类型：TEXT/IMAGE/CODE/TABLE")
    rank: int = Field(..., ge=0, description="片段序号（从0开始）")

    # 标题和内容
    heading: str = Field(..., max_length=500, description="标题/小标题")
    content: str = Field(..., description="内容（纯文本）")
    raw_content: Optional[str] = Field(default=None, description="原始内容（markdown/html）")

    # 图片和统计
    image_url: Optional[str] = Field(default=None, description="图片URL（仅图片类型）")
    length: int = Field(default=0, ge=0, description="内容长度")

    def get_type(self) -> str:
        """获取片段类型"""
        if self.type:
            return self.type
        if self.extra_data and "type" in self.extra_data:
            return self.extra_data["type"]
        return "TEXT"

    def get_length(self) -> int:
        """获取内容长度"""
        if self.length > 0:
            return self.length
        if self.extra_data and "length" in self.extra_data:
            return self.extra_data["length"]
        return len(self.content)


class ArticleCreate(DataFlowBaseModel):
    """创建文章请求"""

    source_config_id: str = Field(..., description="信息源ID")
    title: str = Field(..., min_length=1, max_length=500, description="文章标题")
    content: Optional[str] = Field(default=None, description="文章正文")
    summary: Optional[str] = Field(default=None, description="文章摘要")
    category: Optional[str] = Field(default=None, description="分类")
    tags: Optional[List[str]] = Field(default=None, description="标签")
    extra_data: Optional[Dict[str, Any]] = Field(
        default=None, description="扩展数据")
