# 提示词统一管理最佳实践

## 📋 概述

DataFlow 使用 **PromptManager** 统一管理所有模块的提示词模板，确保：
- ✅ 提示词集中管理，易于维护
- ✅ 支持热更新（修改 YAML 无需重启）
- ✅ 版本控制友好
- ✅ 团队协作方便

## 🗂️ 目录结构

```
prompts/
├── extract.yaml           # 提取模块提示词
├── load.yaml              # 加载模块提示词
└── search.yaml            # 搜索模块提示词（新增）
```

## 📝 模板格式

### YAML 文件结构

```yaml
template_name:
  description: 模板描述
  variables:
    - var1
    - var2
    - var3
  template: |
    模板内容使用 Python format 语法
    变量使用 {var1} 格式
    支持换行和缩进
    {var2} 会被替换为实际值
```

### 示例：search.yaml

```yaml
event_filter:
  description: 使用LLM智能筛选匹配的事项
  variables:
    - events_list
    - query
    - background
    - event_count
    - threshold
  template: |
    你是一个专业的信息检索助手。
    {background}
    ## 检索目标
    {query}
    
    ## 候选事项列表（共{event_count}个）
    {events_list}
```

## 💻 使用方式

### 1. 在模块中使用

```python
from dataflow.core.prompt.manager import PromptManager

class EventSearcher:
    def __init__(self, llm_client, prompt_manager: PromptManager):
        self.prompt_manager = prompt_manager
    
    def build_prompt(self, config):
        # ✅ 使用 PromptManager 渲染模板
        prompt = self.prompt_manager.render(
            "event_filter",
            events_list=events_str,
            query=config.query,
            background=background_section,
            event_count=len(events),
            threshold=config.threshold,
        )
        return prompt
```

### 2. 错误处理（可选）

如果需要在模板缺失时有后备方案：

```python
try:
    prompt = self.prompt_manager.render("event_filter", **variables)
except Exception as e:
    logger.warning(f"模板不存在，使用内置模板: {e}")
    prompt = self._build_default_prompt(**variables)
```

## 🔍 当前模块使用情况

| 模块 | 提示词模板 | 使用方式 | 状态 |
|------|-----------|---------|------|
| **Load** | `article_metadata`, `article_summary` | PromptManager | ✅ 已统一 |
| **Extract** | `event_extraction` | PromptManager + 后备 | ✅ 已统一 |
| **Search** | `event_filter` | PromptManager | ✅ 已统一 |

## ⚠️ 注意事项

### 1. 变量格式

**正确** ✅：
```yaml
template: |
  这是 {variable1} 的示例
  背景信息：{background}
```

**错误** ❌：
```yaml
template: |
  这是 {{ variable1 }} 的示例  # Jinja2 语法，不支持
  {% if background %}           # Jinja2 语法，不支持
```

### 2. 变量声明

必须在 `variables` 列表中声明所有使用的变量：

```yaml
event_filter:
  variables:
    - query          # ✅ 声明
    - background     # ✅ 声明
  template: |
    查询：{query}
    背景：{background}
```

### 3. 缺失变量检查

PromptManager 会自动检查缺失变量：

```python
# 如果模板需要 query 但没有提供
prompt = pm.render("event_filter", background="test")
# ❌ PromptError: 模板'event_filter'缺少必需变量: query
```

## 🛠️ 最佳实践

### 1. 统一使用 PromptManager

❌ **避免硬编码**：
```python
def build_prompt(self, query):
    return f"请搜索：{query}"  # 硬编码
```

✅ **使用模板管理**：
```python
def build_prompt(self, query):
    return self.prompt_manager.render("event_filter", query=query)
```

### 2. 提供合理的默认值

对于可选参数，提供默认值：

```python
prompt = self.prompt_manager.render(
    "event_filter",
    query=config.query,
    background=config.background or "",  # ✅ 默认空字符串
    event_count=len(events),
    threshold=config.threshold,
)
```

### 3. 添加描述和示例

在 YAML 文件中添加详细的描述：

```yaml
event_filter:
  description: |
    使用LLM智能筛选匹配的事项
    
    输入：
    - events_list: 格式化的事项列表字符串
    - query: 用户的检索目标
    - background: 可选的背景信息
    
    输出：
    - matched_indices: 匹配事项的索引数组
```

### 4. 版本控制

将提示词模板纳入版本控制：

```bash
git add prompts/*.yaml
git commit -m "feat(prompts): 添加搜索模块提示词模板"
```

## 📊 模板维护

### 添加新模板

1. 在 `prompts/` 目录创建或编辑 YAML 文件
2. 定义模板名称、变量、内容
3. 在代码中使用 `prompt_manager.render()`
4. 添加单元测试验证模板

### 修改现有模板

1. 直接编辑 YAML 文件
2. 保持变量列表的兼容性
3. 测试确保不破坏现有功能
4. 更新相关文档

### 删除模板

1. 确认没有代码引用该模板
2. 从 YAML 文件中删除
3. 清理相关代码

## 🧪 测试

### 测试模板加载

```python
from dataflow.core.prompt.manager import PromptManager

pm = PromptManager()
templates = pm.list_templates()
print(f"可用模板: {templates}")
```

### 测试模板渲染

```python
prompt = pm.render(
    "event_filter",
    events_list="测试事项",
    query="查找AI",
    background="技术文档",
    event_count=10,
    threshold=0.5,
)
print(prompt)
```

## 📚 参考

- `dataflow/core/prompt/manager.py` - PromptManager 实现
- `dataflow/modules/extract/processor.py` - Extract 模块使用示例
- `dataflow/modules/search/searcher.py` - Search 模块使用示例

## ✅ 检查清单

使用 PromptManager 时，确保：

- [ ] 提示词定义在 YAML 文件中
- [ ] 使用 `{variable}` 格式（不是 `{{ variable }}`）
- [ ] 所有变量在 `variables` 列表中声明
- [ ] 代码中使用 `prompt_manager.render()` 渲染
- [ ] 提供必需的所有变量
- [ ] 可选参数有默认值
- [ ] 添加模板描述和注释

