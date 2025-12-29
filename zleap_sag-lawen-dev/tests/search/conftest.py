"""
Stage1 搜索模块测试配置

专门处理搜索模块的异步事件循环和数据库连接问题
"""

import asyncio
import pytest
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock


@pytest.fixture(scope="function")
async def async_session():
    """
    创建一个模拟的异步数据库会话
    用于测试中避免真实的数据库连接问题
    """
    from sqlalchemy.ext.asyncio import AsyncSession
    mock_session = AsyncMock(spec=AsyncSession)

    # 模拟 execute 方法
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_session.execute.return_value = mock_result

    yield mock_session


@pytest.fixture(scope="function")
def mock_database_session():
    """
    完全模拟数据库会话，避免任何真实的数据库连接
    """
    mock_session = MagicMock()
    mock_session.execute = AsyncMock()
    mock_session.commit = AsyncMock()
    mock_session.rollback = AsyncMock()
    mock_session.close = AsyncMock()

    return mock_session


# 标记定义
pytest.mark.search_tests = pytest.mark.search_tests
pytest.mark.integration = pytest.mark.integration
pytest.mark.unit = pytest.mark.unit