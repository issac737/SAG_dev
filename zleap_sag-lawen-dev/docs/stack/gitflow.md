# Git 协作指南

## 分支结构

```
main                        # 线上稳定版本
  │
  └── dev                   # 开发主线
       ├── feat/<功能>      # 功能开发
       ├── exp/<算法>       # 算法实验（保留多版本）
       ├── fix/<问题>       # Bug 修复
       └── <姓名>/<功能>    # 个人开发
```

## 命名规范

| 类型 | 格式 | 示例 |
|------|------|------|
| 功能 | `feat/<功能>` | `feat/search-opt` |
| 实验 | `exp/<算法>-v<版本>` | `exp/pagerank-v2` |
| 修复 | `fix/<问题>` | `fix/es-timeout` |
| 测试 | `test/<数据集>` | `test/hotpotqa` |

## 开发流程

```bash
# 1. 更新 dev
git checkout dev && git pull

# 2. 创建分支
git checkout -b feat/my-feature

# 3. 提交
git commit -m "feat: 添加xxx功能"

# 4. 推送 & PR
git push origin feat/my-feature
```

## 版本标记

```bash
# 功能版本
git tag -a v1.0.0 -m "首个稳定版本"

# 测试基准（记录测试结果）
git tag -a test/hotpot-v1 -m "召回率 72%, 准确率 68%"

# 推送标签
git push origin --tags
```

## Commit 规范

```
feat:     新功能
fix:      Bug 修复
test:     测试相关
refactor: 重构
docs:     文档
chore:    构建/工具
```

## 分支清理

```bash
# 删除已合并分支
git branch --merged dev | grep -v "dev\|main" | xargs git branch -d

# 删除远程分支
git push origin --delete <branch>
```

## 保留策略

| 保留 | 可删除 |
|------|--------|
| `main`, `dev` | 已合并的 `feat/*`, `fix/*` |
| 所有 `test/*` 标签 | 过时的临时分支 |
| 最新的 `exp/*` 实验分支 | 失败的实验分支 |
