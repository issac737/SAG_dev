# 🚀 DataFlow API - 5分钟快速启动

## Step 1: 安装依赖 (1分钟)
```bash
uv pip install -e "."
```

## Step 2: 配置环境 (1分钟)
```bash
cp .env.example .env
# 编辑 .env, 设置:
# LLM_API_KEY=sk-your-key
```

## Step 3: 启动服务 (1分钟)
```bash
python -m dataflow.api.main
```

## Step 4: 测试 API (2分钟)
访问: http://localhost:8000/api/docs

### 快速测试命令:
```bash
# 创建信息源
curl -X POST http://localhost:8000/api/v1/sources \
  -H "Content-Type: application/json" \
  -d '{"name": "测试库"}'

# 查看默认实体类型
curl http://localhost:8000/api/v1/entity-types/defaults
```

## 🎉 完成！
现在可以开发 Web UI 了！

详细文档: docs/api.md
