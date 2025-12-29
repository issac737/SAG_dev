"""
事项转段落工具

功能：
1. 从事项列表中提取事项 ID
2. 查询数据库获取事项的 references、article_id、source_config_id
3. 通过 references 查询 ArticleSection 表获取段落内容

使用示例:
    from event_to_sections import EventToSectionConverter

    converter = EventToSectionConverter()

    # 方式1: 从事项字典列表获取段落
    events = pipeline.search_events(...)
    sections = await converter.get_sections_from_events(events)

    # 方式2: 从事项ID列表获取段落
    event_ids = ["event-id-1", "event-id-2"]
    sections = await converter.get_sections_by_event_ids(event_ids)
"""

from dataflow.core.config.settings import Settings
from dataflow.db.models import SourceEvent, ArticleSection
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import select
import asyncio
from typing import List, Dict, Any, Optional
from pathlib import Path
import sys

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


class EventToSectionConverter:
    """事项到段落转换器"""

    def __init__(self, db_url: Optional[str] = None):
        """
        初始化转换器

        Args:
            db_url: 数据库连接 URL，如果不提供则从配置读取
        """
        if db_url is None:
            settings = Settings()
            db_url = settings.mysql_url

        # 创建异步引擎
        self.engine = create_async_engine(db_url, echo=False)
        self.async_session = async_sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False
        )

    async def close(self):
        """关闭数据库连接"""
        await self.engine.dispose()

    async def get_sections_from_events(
        self,
        events: List[Dict[str, Any]],
        include_event_info: bool = True
    ) -> List[Dict[str, Any]]:
        """
        从事项列表获取关联的段落

        Args:
            events: 事项列表（API 返回的字典格式）
            include_event_info: 是否在结果中包含事项信息

        Returns:
            段落列表，每个段落包含：
            - section_id: 段落ID
            - article_id: 文章ID
            - rank: 段落序号
            - heading: 标题
            - content: 内容
            - event_id: 关联的事项ID（如果 include_event_info=True）
            - event_title: 事项标题（如果 include_event_info=True）
        """
        # 提取事项ID
        event_ids = [e.get('id') for e in events if e.get('id')]

        if not event_ids:
            return []

        # 查询数据库
        return await self.get_sections_by_event_ids(
            event_ids,
            include_event_info=include_event_info,
            events_dict={e['id']: e for e in events if e.get('id')}
        )

    async def get_sections_by_event_ids(
        self,
        event_ids: List[str],
        include_event_info: bool = True,
        events_dict: Optional[Dict[str, Dict]] = None
    ) -> List[Dict[str, Any]]:
        """
        通过事项ID列表获取关联的段落

        Args:
            event_ids: 事项ID列表
            include_event_info: 是否在结果中包含事项信息
            events_dict: 事项信息字典（可选，避免重复查询）

        Returns:
            段落列表
        """
        if not event_ids:
            return []

        async with self.async_session() as session:
            # 1. 查询事项，获取 references 和其他信息
            query = select(SourceEvent).where(SourceEvent.id.in_(event_ids))
            result = await session.execute(query)
            events = result.scalars().all()

            # 2. 收集所有被引用的 section_ids
            event_to_sections_map = {}  # event_id -> [section_ids]
            all_section_ids = set()

            for event in events:
                if event.references and isinstance(event.references, list):
                    event_to_sections_map[event.id] = event.references
                    all_section_ids.update(event.references)
                else:
                    event_to_sections_map[event.id] = []

            if not all_section_ids:
                print("⚠️  没有找到任何段落引用 (references 字段为空)")
                return []

            # 3. 查询所有段落
            section_query = (
                select(ArticleSection)
                .where(ArticleSection.id.in_(all_section_ids))
                .order_by(ArticleSection.article_id, ArticleSection.rank)
            )
            section_result = await session.execute(section_query)
            sections = section_result.scalars().all()

            # 4. 构建 section_id -> section 映射
            section_dict = {s.id: s for s in sections}

            # 5. 构建结果列表
            result_sections = []

            for event in events:
                section_ids = event_to_sections_map.get(event.id, [])

                for section_id in section_ids:
                    section = section_dict.get(section_id)
                    if not section:
                        continue

                    section_data = {
                        'section_id': section.id,
                        'article_id': section.article_id,
                        'rank': section.rank,
                        'heading': section.heading,
                        'content': section.content,
                        'extra_data': section.extra_data
                    }

                    if include_event_info:
                        section_data['event_id'] = event.id
                        section_data['event_title'] = event.title
                        section_data['event_summary'] = event.summary

                        # 如果提供了 events_dict，添加更多事项信息
                        if events_dict and event.id in events_dict:
                            section_data['event_score'] = events_dict[event.id].get(
                                'score', 0)

                    result_sections.append(section_data)

            return result_sections

    async def get_event_details_with_sections(
        self,
        event_ids: List[str]
    ) -> List[Dict[str, Any]]:
        """
        获取事项的完整信息（包括关联的段落）

        Args:
            event_ids: 事项ID列表

        Returns:
            事项列表，每个事项包含完整的段落信息
        """
        if not event_ids:
            return []

        async with self.async_session() as session:
            # 查询事项
            query = select(SourceEvent).where(SourceEvent.id.in_(event_ids))
            result = await session.execute(query)
            events = result.scalars().all()

            # 收集所有 section_ids
            all_section_ids = set()
            for event in events:
                if event.references and isinstance(event.references, list):
                    all_section_ids.update(event.references)

            # 查询段落
            section_dict = {}
            if all_section_ids:
                section_query = select(ArticleSection).where(
                    ArticleSection.id.in_(all_section_ids)
                )
                section_result = await session.execute(section_query)
                sections = section_result.scalars().all()
                section_dict = {s.id: s for s in sections}

            # 构建结果
            result_events = []
            for event in events:
                event_data = {
                    'event_id': event.id,
                    'source_config_id': event.source_config_id,
                    'article_id': event.article_id,
                    'title': event.title,
                    'summary': event.summary,
                    'content': event.content,
                    'rank': event.rank,
                    'start_time': event.start_time.isoformat() if event.start_time else None,
                    'end_time': event.end_time.isoformat() if event.end_time else None,
                    'created_time': event.created_time.isoformat() if event.created_time else None,
                    'sections': []
                }

                # 添加关联的段落
                if event.references:
                    for section_id in event.references:
                        section = section_dict.get(section_id)
                        if section:
                            event_data['sections'].append({
                                'section_id': section.id,
                                'rank': section.rank,
                                'heading': section.heading,
                                'content': section.content,
                                'extra_data': section.extra_data
                            })

                    # 按 rank 排序
                    event_data['sections'].sort(key=lambda x: x['rank'])

                result_events.append(event_data)

            return result_events


async def demo():
    """示例用法"""

    # 创建转换器
    converter = EventToSectionConverter()

    try:
        # 示例：从事项ID获取段落
        event_ids = ["your-event-id-1", "your-event-id-2"]

        print("=" * 60)
        print("获取事项关联的段落")
        print("=" * 60)

        sections = await converter.get_sections_by_event_ids(event_ids)

        print(f"\n找到 {len(sections)} 个段落\n")

        for i, section in enumerate(sections, 1):
            print(f"{i}. 段落 {section['rank']}: {section['heading']}")
            print(f"   事项: {section.get('event_title', 'N/A')}")
            print(f"   内容预览: {section['content'][:100]}...")
            print()

        # 示例：获取事项完整信息
        print("=" * 60)
        print("获取事项完整信息（包括段落）")
        print("=" * 60)

        events = await converter.get_event_details_with_sections(event_ids)

        for event in events:
            print(f"\n事项: {event['title']}")
            print(f"段落数: {len(event['sections'])}")
            for section in event['sections']:
                print(f"  - {section['heading']}")

    finally:
        await converter.close()


if __name__ == "__main__":
    asyncio.run(demo())
