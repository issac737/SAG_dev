# 搜索结果 AI 智能总结功能

## 🎯 功能概述

在搜索页面增加 AI 智能总结板块，自动总结搜索结果，提供流式输出的分析和总结。

---

## 📊 已实现的功能

### 后端 API

**Endpoint**: `POST /api/v1/pipeline/summarize`

**请求参数**:
```json
{
  "source_config_id": "source-uuid",
  "query": "用户查询",
  "event_ids": ["event-id-1", "event-id-2", ...]
}
```

**响应**: Server-Sent Events (SSE) 流式响应

**事件类型**:
- `event: thinking` - 思考过程（data: 思考内容）
- `event: content` - 总结内容（data: 总结文本）
- `event: error` - 错误信息（data: 错误描述）
- `event: done` - 完成标记

---

### 前端组件

**组件**: `web/components/search/AISummary.tsx`

**Props**:
```typescript
{
  sourceId: string,      // 信息源ID
  query: string,         // 用户查询
  eventIds: string[],    // 事项ID列表
  className?: string     // 可选样式
}
```

**特点**:
- ✅ 渐变背景（蓝色→紫色渐变）
- ✅ 流式动画效果
- ✅ 思考过程展示
- ✅ 打字机效果
- ✅ macOS 风格设计
- ✅ 响应式布局
- ✅ 暗黑模式支持

---

## 🚀 使用方式

### 在搜索页面使用

1. 用户在搜索框输入查询
2. 点击搜索按钮
3. 返回搜索结果后，自动显示 AI 总结板块
4. AI 实时流式输出思考过程和总结内容

**位置**:
- 搜索框下方
- 搜索结果列表上方

---

## 💡 实现细节

### 后端流程

1. **接收请求** - 获取 source_config_id, query, event_ids
2. **查询数据** - 根据 event_ids 查询完整事项数据和 references
3. **创建 Agent** - 使用 SummarizerAgent
4. **流式总结** - 实时推送思考和内容

### SummarizerAgent 特性

- ✅ 自动为事项添加序号 (order: 1, 2, 3...)
- ✅ 自动添加待办任务（要求引用序号）
- ✅ LLM 回答中自动引用 [#1], [#2], [#3]
- ✅ 默认流式输出

### 前端流程

1. **监听事项变化** - useEffect 监听 eventIds
2. **发起 SSE 请求** - fetch API 连接后端
3. **解析 SSE 流** - ReadableStream 读取事件
4. **实时更新UI** - setState 更新思考和内容
5. **动画效果** - framer-motion 流畅动画

---

## 🎨 UI 设计

### 样式特点

**颜色方案**:
- 主背景：蓝色→紫色渐变
- 思考框：紫色→粉色渐变
- 内容框：白色半透明
- 图标：蓝色系

**动画效果**:
- 入场动画：淡入 + 上移
- 思考框：展开动画
- 光标：闪烁效果
- 完成标记：弹跳效果

**图标**:
- Sparkles - AI 总结图标
- Brain - 思考过程图标
- Lightbulb - 灵感图标
- CheckCircle2 - 完成标记

---

## 🧪 测试步骤

### 1. 启动后端

```bash
cd dataflow
uv run uvicorn dataflow.api.main:app --reload
```

### 2. 启动前端

```bash
cd web
npm run dev
```

### 3. 测试流程

1. 访问 `http://localhost:3000/search`
2. 选择信息源
3. 输入查询（如："总结骑手的技能要求"）
4. 点击搜索
5. 查看搜索结果
6. **在搜索框下方查看 AI 智能总结板块**
7. 观察流式输出效果

### 预期结果

- ✅ 搜索结果正常显示
- ✅ AI 总结板块出现在搜索框下方
- ✅ 思考过程实时流式输出
- ✅ 总结内容实时流式输出
- ✅ 回答中包含序号引用 [#1], [#2], [#3]
- ✅ 完成后显示绿色勾选标记

---

## 📝 技术栈

### 后端
- FastAPI StreamingResponse
- Server-Sent Events (SSE)
- SummarizerAgent
- EventRepository

### 前端
- React 18 + TypeScript
- Framer Motion（动画）
- Tailwind CSS（样式）
- Server-Sent Events API

---

## ✨ 示例输出

**查询**: "总结外卖骑手的岗位技能要求"

**思考过程**:
```
扫描文档事项分区，共有3条相关文档
提取关键信息：岗位专用性技能、数字技能、时空规划
按业务逻辑组织内容
使用序号标注信息来源
```

**总结内容**:
```
外卖骑手岗位技能要求总结：

1. 岗位专用性技能
   - 数字技能：熟练使用外卖平台App [#1]
   - 即时时空规划技能：路线优化和时间管理 [#1]

2. 基础技能要求
   - 骑行技能和交通规则 [#2]
   - 客户沟通能力 [#3]

3. 发展趋势
   - 技能要求持续提升 [#2]
   - 数字化工具应用增加 [#3]
```

---

## 🔧 配置选项

### agent.json

SummarizerAgent 会使用 `prompts/agent.json` 的配置：

```json
{
  "config": {
    "output": {
      "stream": false,
      "think": true,
      "format": "markdown",
      "style": "专业、严谨、可靠"
    }
  }
}
```

### 自定义样式

修改 `AISummary.tsx` 中的 className 可以自定义样式。

---

## ✅ 完成清单

- [x] 后端 API endpoint
- [x] 流式 SSE 响应
- [x] SummarizerAgent 集成
- [x] 前端 AISummary 组件
- [x] macOS 风格设计
- [x] 流式动画效果
- [x] 集成到搜索页面
- [x] 暗黑模式支持

---

## 🎯 下一步优化

1. 添加"复制总结"按钮
2. 添加"导出为Markdown"功能
3. 支持自定义总结风格
4. 添加总结历史记录
5. 支持手动选择事项进行总结

---

**搜索结果 AI 智能总结功能已完成！** 🎉

