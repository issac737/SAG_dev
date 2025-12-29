# NLTK Data 目录

此目录包含预下载的 NLTK 数据，用于加速 Docker 构建过程。

## 为什么需要这个？

在 Docker 构建时，如果每次都从网络下载 NLTK 数据：
- ❌ 构建速度慢（每次需要下载 ~25MB）
- ❌ 依赖网络连接
- ❌ 在网络受限的服务器上无法构建

通过预下载并提交到 git：
- ✅ 构建速度快（直接 COPY，几秒钟完成）
- ✅ 离线可用
- ✅ 版本一致

## 包含的数据

- **punkt**: 句子分词器（~13MB）
- **punkt_tab**: 新版句子分词器（~12MB）

总大小：约 25MB

## 如何更新 NLTK 数据

如果需要添加新的 NLTK 资源或更新现有资源：

```bash
# 1. 运行下载脚本
python scripts/download_nltk_data.py

# 2. 提交更新
git add nltk_data/
git commit -m "Update NLTK data"
git push
```

## 使用方式

NLTK 数据会在 Docker 构建时自动复制到容器的 `/root/nltk_data/` 目录，NLTK 库会自动找到并使用这些数据。

无需任何额外配置！

