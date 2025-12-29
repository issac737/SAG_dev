# LLM 缓存测试运行指南

## 📋 前置条件

### 1. 确保 Redis 正在运行

```bash
# Windows 环境
# 如果使用 WSL 安装的 Redis
wsl redis-server

# 或者使用 Windows 原生 Redis（如果已安装）
redis-server
```

### 2. 检查 .env 配置

确保项目根目录的 `.env` 文件包含以下配置：

```bash
# Redis 配置
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=  # 如果没有密码就留空
REDIS_DB=0

# LLM 配置
LLM_API_KEY=你的API密钥
LLM_MODEL=sophnet/Qwen3-30B-A3B-Thinking-2507
LLM_BASE_URL=https://api.302.ai/v1  # 或其他中转服务

# LLM 缓存配置（可选，有默认值）
LLM_CACHE_ENABLED=true
LLM_CACHE_PREFIX=llm:cache:
CACHE_LLM_TTL=604800
```

## 🚀 运行方式

### 方式 1：在 VSCode 中运行（推荐）

1. 打开 `test_llm_cache.py` 文件
2. 右键点击编辑器 -> 选择 **"在终端中运行 Python 文件"**
3. 或者按 **Ctrl + F5** 运行

### 方式 2：使用终端命令

在项目根目录打开终端，运行：

```bash
# Windows PowerShell
python test_llm_cache.py

# 或者使用 python3
python3 test_llm_cache.py
```

### 方式 3：在 VSCode 调试模式运行

1. 在 `test_llm_cache.py` 文件中按 **F5** 启动调试
2. 可以设置断点查看缓存执行过程

## 📊 预期输出

成功运行后，你应该看到类似这样的输出：

```
======================================================================
📋 LLM 缓存配置
======================================================================
✅ 缓存启用: True
🔑 键前缀: llm:cache:
⏰ TTL: 604800 秒 (7 天)
🤖 模型: sophnet/Qwen3-30B-A3B-Thinking-2507
🌐 API 地址: https://api.302.ai/v1
======================================================================

正在创建 LLM 客户端...
✅ LLM 客户端创建成功

======================================================================
🚀 第一次调用 - 应该调用 LLM API（缓存未命中）
======================================================================
INFO:ai.cache:❌ LLM 缓存未命中 - 模型: sophnet/Qwen3-30B-A3B-Thinking-2507
INFO:ai.openai:🤖 调用 LLM - 模型: sophnet/Qwen3-30B-A3B-Thinking-2507...
✅ 响应成功
📝 内容: Python 是一种高级、解释型、通用编程语言...
📊 Token 使用: 输入=20, 输出=50, 总计=70
🏁 完成原因: stop

======================================================================
🎯 第二次调用 - 应该从缓存返回（缓存命中）
======================================================================
INFO:ai.cache:✅ LLM 缓存命中 - 模型: sophnet/Qwen3-30B-A3B-Thinking-2507, 键: llm:cache:a1b2c3d4...
✅ 响应成功
📝 内容: Python 是一种高级、解释型、通用编程语言...
📊 Token 使用: 输入=20, 输出=50, 总计=70
🏁 完成原因: stop

✅ 缓存验证通过 - 两次响应内容完全一致

======================================================================
🧹 清理缓存测试
======================================================================
INFO:ai.cache:已清理 1 个 LLM 缓存条目 (模式: llm:cache:*)
✅ 已清理 1 个缓存条目

======================================================================
✨ 所有测试完成！
======================================================================
```

## 🔍 关键观察点

1. **第一次调用**：
   - 日志显示 "❌ LLM 缓存未命中"
   - 日志显示 "🤖 调用 LLM"
   - 说明真正调用了 LLM API

2. **第二次调用**：
   - 日志显示 "✅ LLM 缓存命中"
   - **没有** "🤖 调用 LLM" 日志
   - 说明直接从缓存返回，速度更快

3. **内容一致性**：
   - 两次响应的内容完全相同
   - 验证缓存正常工作

## ❗ 常见问题

### 1. 导入错误

```
ModuleNotFoundError: No module named 'dataflow'
```

**解决**：确保在项目根目录运行，或者安装项目依赖：
```bash
pip install -e .
```

### 2. Redis 连接失败

```
ConnectionRefusedError: [WinError 10061] No connection could be made
```

**解决**：
- 检查 Redis 是否正在运行
- 检查 `.env` 中的 Redis 配置是否正确

### 3. LLM API 调用失败

```
LLMError: OpenAI调用失败: ...
```

**解决**：
- 检查 `LLM_API_KEY` 是否正确
- 检查 `LLM_BASE_URL` 是否可访问
- 检查网络连接

### 4. 缓存未生效

如果两次都调用了 LLM API，检查：
- `.env` 中 `LLM_CACHE_ENABLED=true`
- Redis 是否正常运行
- 查看日志中的错误信息

## 🛠️ 调试技巧

### 查看详细日志

修改 `.env` 中的日志级别：

```bash
LOG_LEVEL=DEBUG
```

### 手动检查 Redis 缓存

```bash
# 连接 Redis CLI
redis-cli

# 查看所有 LLM 缓存键
keys llm:cache:*

# 查看某个缓存内容
get llm:cache:xxxxx

# 清空所有缓存
flushdb
```

### 监控 Redis 操作

在另一个终端运行：

```bash
redis-cli monitor
```

可以实时看到所有 Redis 操作。

## 📚 下一步

测试成功后，LLM 缓存会自动在你的整个项目中生效，包括：

- API 调用 (`/api/v1/chat`)
- Agent 推理
- 文档提取
- 搜索优化

所有使用 `OpenAIClient.chat()` 的地方都会自动享受缓存加速！
