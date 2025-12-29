# 搜索参数配置 UI 优化

## 概述
优化了搜索参数配置界面，添加了 localStorage 持久化、改进了样式和交互体验。采用简洁的逻辑：配置自动加载，手动保存。

## 实现的功能

### 1. localStorage 持久化 ✅
创建了 `web/lib/search-params-storage.ts` 工具库，提供：
- `saveSearchParams()` - 保存配置到 localStorage
- `loadSearchParams()` - 从 localStorage 加载配置

### 2. 简洁的保存机制 ✅
- **自动加载**: 打开抽屉时自动加载上次保存的配置
- **手动保存**: 点击"保存配置"按钮保存到 localStorage
- **自动关闭**: 保存成功后自动关闭抽屉
- **Toast 通知**: 所有操作都有即时反馈

### 3. 全面的样式优化 ✅

#### 视觉层次
- 改进抽屉头部：渐变背景、更好的间距
- 增强 Tabs 样式：更明显的活动状态、圆角背景
- 参数卡片化：每个参数都有独立的卡片容器
- 区分布尔和数字参数的视觉样式

#### 动画和交互
- 参数列表渐入动画（staggered animation）
- 卡片悬停效果
- 按钮状态过渡
- 平滑的参数值变化

### 4. 优化的抽屉底部 ✅
简洁的操作按钮布局：
```
[     保存配置     ] [→]
      主按钮      关闭
```

- **保存配置** - 蓝色主按钮，保存后自动关闭抽屉
- **重置** - 头部按钮，恢复默认配置
- **关闭** - 关闭抽屉

## 技术细节

### 状态管理
```typescript
// 初始化时从 localStorage 加载
const [searchParams, setSearchParams] = useState(() => {
  const loadedParams = loadSearchParams()
  return loadedParams || getDefaultSearchParams()
})

// 保存到 localStorage 并关闭抽屉
const handleSaveParams = () => {
  saveSearchParams(searchParams)
  toast.success('配置已保存')
  setDrawerOpen(false)
}
```

### localStorage 键
- `search-params` - 存储搜索参数配置

### Toast 通知
使用 `sonner` 库提供用户反馈：
- ✅ "配置已保存"
- ✅ "已重置为默认配置"
- ❌ "保存失败，请重试"

## 文件修改清单

1. **新建文件**
   - `web/lib/search-params-storage.ts` - localStorage 工具库

2. **修改文件**
   - `web/app/search/page.tsx`
     - 初始化时从 localStorage 加载配置
     - 添加 handleSaveParams（保存并关闭）
     - 优化 DrawerHeader（渐变背景）
     - 优化 Tabs 和参数卡片样式
     - 简化 DrawerFooter（保存 + 关闭）
   - `web/components/documents/DocumentDetailDrawer.tsx`
     - 修复 TypeScript 类型错误

## UI/UX 改进

### 交互流程
1. **打开配置**: 自动显示上次保存的配置
2. **调整参数**: 实时预览，可用于搜索
3. **保存配置**: 点击保存 → Toast 提示 → 自动关闭
4. **重置配置**: 点击重置 → 恢复默认值
5. **下次使用**: 自动加载保存的配置

### 设计原则
- ✅ **简单直接**: 配置自动加载，一键保存
- ✅ **即时反馈**: Toast 通知所有操作
- ✅ **视觉清晰**: 卡片化设计，层次分明
- ✅ **流畅动画**: 平滑过渡和悬停效果

## 用户场景

1. **首次使用**
   - 打开抽屉 → 显示默认配置
   - 调整参数 → 点击保存
   - 配置保存 → 抽屉自动关闭

2. **日常使用**
   - 打开抽屉 → 自动显示上次配置
   - 直接搜索 → 使用当前配置
   - 或调整后保存 → 更新配置

3. **恢复默认**
   - 点击重置 → 恢复默认值
   - 可选择保存或直接使用

## 浏览器兼容性
- 使用标准 localStorage API
- 支持所有现代浏览器
- 优雅降级（localStorage 不可用时仍可使用，只是不会持久化）

## 性能优化
- 初始化时直接从 localStorage 加载（避免额外渲染）
- 动画使用 Framer Motion 的硬件加速
- 参数变化使用内置防抖
