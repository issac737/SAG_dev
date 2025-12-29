# AI 智能总结功能 - 完整实现

## ✅ 已实现功能

### 后端 API

**Endpoint**: `POST /api/v1/pipeline/summarize`

**功能**:
- ✅ 根据 event_ids 查询完整事项数据
- ✅ 集成 SummarizerAgent
- ✅ Server-Sent Events (SSE) 流式响应
- ✅ 自动添加事项序号
- ✅ 错误处理和日志

**请求格式**:
```json
{
  "source_config_id": "source-uuid",
  "query": "用户查询",
  "event_ids": ["event-id-1", "event-id-2", ...]
}
```

**响应格式** (SSE):
- `event: thinking` - 思考过程
- `event: content` - 总结内容
- `event: error` - 错误信息
- `event: done` - 完成标记

---

### 前端 UI

**组件**: `web/components/search/AISummary.tsx`

**优化后的特性**:

#### 1. 思考框优化
- ✅ 默认显示最后 5 行（max-h-24）
- ✅ 可展开/收起（max-h-64）
- ✅ 自动滚动到底部
- ✅ 展开/收起按钮
- ✅ 精简的头部设计

#### 2. 引用渲染优化
- ✅ `[#1]`, `[#2]`, `[#3]` 渲染为蓝色圆角标签
- ✅ hover 悬停效果
- ✅ 点击触发回调
- ✅ 自动映射序号到 event_id

#### 3. 样式优化
- ✅ 图标：蓝色渐变方块背景（8x8px）
- ✅ 思考框：紫色→粉色渐变，可折叠
- ✅ 内容框：白色半透明
- ✅ 引用标签：蓝色标签，可点击
- ✅ 精简padding和间距
- ✅ 统一圆角（rounded-lg）

#### 4. 交互优化
- ✅ 点击引用 `[#1]` 打开事项详情抽屉
- ✅ 序号自动映射：order 1 → eventIds[0]
- ✅ 流畅的动画过渡
- ✅ macOS 风格设计

---

## 🎨 UI 设计细节

### 配色方案

```css
主卡片背景: 
  from-blue-50/60 via-indigo-50/30 to-white
  (浅色模式：蓝色→紫色→白色渐变)

思考框:
  from-purple-50/60 to-pink-50/40
  (紫色→粉色渐变)

内容框:
  bg-white/60 (白色60%透明度)

引用标签:
  bg-blue-100 text-blue-700
  hover:bg-blue-200
```

### 尺寸规范

```css
图标方块: w-8 h-8
标题字体: text-base font-semibold
思考框默认高度: max-h-24 (约5行)
思考框展开高度: max-h-64
内容框padding: p-4
外层padding: p-5 sm:p-6
```

---

## 🚀 使用流程

### 1. 用户搜索

```
用户输入: "@测试文档 美团骑手的技能"
↓
点击搜索
↓
返回 5 条搜索结果
```

### 2. 自动触发 AI 总结

```
搜索结果返回
↓
提取所有 event_ids: ["id1", "id2", ...]
↓
自动调用 /api/v1/pipeline/summarize
↓
流式显示在搜索框下方
```

### 3. 交互体验

```
思考过程（紫色框）
↓ 实时流式输出
总结内容（白色框）
↓ 包含引用标签
点击 [#1] [#2] [#3]
↓
打开对应事项的详情抽屉
```

---

## 💡 技术实现

### 引用点击流程

```typescript
1. 渲染内容时，将 [#数字] 转为可点击标签:
   "[#1]" → <span class="reference-tag" data-order="1">[#1]</span>

2. 点击事件监听:
   onClick → 检测 classList.contains('reference-tag')

3. 提取序号并映射:
   data-order="1" → order = 1
   eventIds[order - 1] → eventId

4. 触发回调:
   onReferenceClick(eventId)

5. 打开抽屉:
   setSelectedEventId(eventId)
   setIsDetailDrawerOpen(true)
```

### 思考框滚动

```typescript
1. 默认状态:
   - max-h-24 (约5行高度)
   - overflow-y-auto
   - 自动滚动到底部

2. 展开状态:
   - max-h-64 (更高)
   - 手动滚动

3. 自动滚动逻辑:
   useEffect(() => {
     if (!isThinkingExpanded) {
       thinkingRef.current.scrollTop = scrollHeight
     }
   }, [thinking])
```

---

## 📊 样式对比

### 优化前
- 思考框：完全展开，占用空间大
- 引用：纯文本，无法点击
- 配色：渐变过重
- 间距：过大，不够紧凑

### 优化后
- ✅ 思考框：默认5行，可展开/收起
- ✅ 引用：蓝色标签，可点击查看
- ✅ 配色：精简优雅，蓝紫色系
- ✅ 间距：紧凑合理，更高效

---

## 🎯 效果演示

### 思考过程
```
┌─────────────────────────────────────┐
│ 🧠 思考过程          [展开▼]        │
├─────────────────────────────────────┤
│ ...                                 │
│ 提取关键指标                         │
│ 按业务逻辑组织                       │  ← 默认显示
│ 使用序号标注                         │     最后5行
│ ▊                                   │  ← 光标闪烁
└─────────────────────────────────────┘
```

### 总结内容
```
┌─────────────────────────────────────┐
│ 美团骑手技能总结：                   │
│                                     │
│ 1. 数字技能 [#1]  ← 蓝色标签，可点击  │
│ 2. 时空规划能力 [#2]                │
│ 3. 客户服务技能 [#3][#4]            │
│                                     │
│ 综合来看...                         │
└─────────────────────────────────────┘
```

---

## ✅ 完成清单

- [x] 后端 API（流式SSE）
- [x] 前端组件（AISummary.tsx）
- [x] 思考框滚动（默认5行）
- [x] 展开/收起功能
- [x] 引用渲染（蓝色标签）
- [x] 引用点击（打开抽屉）
- [x] 序号映射（order → event_id）
- [x] 样式优化（精简配色）
- [x] macOS 风格设计
- [x] 暗黑模式支持

---

**AI 智能总结功能已完全优化！** 🎉

