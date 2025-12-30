# 提示词对比测试说明

## 📁 文件结构

```
tests/extract/test_extract_prompt/
├── test_extract.py                    # 测试脚本（主程序）
├── extract_v2.yaml                    # 增强版提示词
├── 林俊杰女友照片经常被识别为AI林俊杰官宣恋情.md  # 测试文件
└── README.md                          # 本说明文档
```

---

## 🚀 使用步骤

### 1. 填写配置

打开 `test_extract.py`，修改顶部的配置区域：

```python
# ==================== 配置区域（请手动填写） ====================

# 测试文件路径（已默认填写）
TEST_FILE_PATH = r"C:\Users\PC\Desktop\zleap_sag-lawen-dev\zleap_sag-lawen-dev\tests\extract\test_extract_prompt\林俊杰女友照片经常被识别为AI林俊杰官宣恋情.md"

# Source Config ID（可选，如果不需要可以留空）
SOURCE_CONFIG_ID = "你的source_config_id"

# LLM 配置（必填）
LLM_API_KEY = "sk-xxxxxxxxxxxxxxxx"      # 你的 API 密钥
LLM_BASE_URL = "https://api.openai.com/v1"  # 你的 LLM 地址
LLM_MODEL = "qwen-plus"                  # 模型名称

# 提示词文件路径（已默认填写）
PROMPT_V1 = r"C:\Users\PC\Desktop\zleap_sag-lawen-dev\zleap_sag-lawen-dev\prompts\extract.yaml"
PROMPT_V2 = r"C:\Users\PC\Desktop\zleap_sag-lawen-dev\zleap_sag-lawen-dev\tests\extract\test_extract_prompt\extract_v2.yaml"

# ================================================================
```

### 2. 运行测试

```bash
cd C:\Users\PC\Desktop\zleap_sag-lawen-dev\zleap_sag-lawen-dev
python tests\extract\test_extract_prompt\test_extract.py
```

### 3. 查看结果

测试脚本会自动：
- ✅ 测试原版提示词（extract.yaml）
- ✅ 测试增强版提示词（extract_v2.yaml）
- ✅ 对比两个版本的过滤效果
- ✅ 输出统计报告

---

## 📊 输出示例

```
================================================================================
📊 对比结果
================================================================================

指标                  原版(v1)        增强版(v2)      对比
--------------------------------------------------------------------------------
总提取事项           30              30              0
✅ 有效事项           1               1               0
❌ 过滤事项           5               25              +20
过滤率               16.7%          83.3%          +66.6%
典型噪音过滤         2              8              +6

================================================================================
💡 结论
================================================================================

✅ 增强版效果更好！
   - 多过滤了 20 个噪音事项
   - 过滤率提升 66.6%
   - 典型噪音识别增加 6 个

建议:
  → 建议使用增强版提示词
```

---

## 🔍 测试内容

### 测试文件特点

**有效内容**（应提取）：
- 核心新闻：林俊杰官宣恋情
- 内容描述：女友七七的特征、网友反应

**噪音内容**（应过滤）：
- ❌ 导航菜单（第1-27行）：新浪首页、新闻、体育、财经...
- ❌ 用户操作（第28-32行）：我的收藏、注册、登录
- ❌ 平台标识（第34行）：新浪新闻客户端
- ❌ 营销文案（第60行）：投资热点尽在新浪财经APP
- ❌ 推荐链接（第66-108行）：阅读排行榜、图片新闻...

### 预期结果

**成功的标志**：
1. ✅ 有效事项 = 1（只提取核心新闻）
2. ✅ 增强版过滤率 > 80%（原版通常 < 30%）
3. ✅ 典型噪音被正确识别（导航、按钮、推荐等）

---

## ⚙️ 配置说明

### LLM 配置

**从 .env 文件获取**（推荐）：

```python
import os
from dotenv import load_dotenv

load_dotenv()

LLM_API_KEY = os.getenv("LLM_API_KEY")
LLM_BASE_URL = os.getenv("LLM_BASE_URL")
LLM_MODEL = os.getenv("LLM_MODEL", "qwen-plus")
```

**直接填写**（快速测试）：
- `LLM_API_KEY`：你的 API 密钥
- `LLM_BASE_URL`：LLM 服务地址
- `LLM_MODEL`：模型名称（qwen-plus）

### 提示词文件

- **PROMPT_V1**：原版提示词（`prompts/extract.yaml`）
- **PROMPT_V2**：增强版提示词（本目录的 `extract_v2.yaml`）

---

## 📝 注意事项

### 1. API 限流

测试脚本在两次调用之间有 2 秒延迟：
```python
await asyncio.sleep(2)
```

如果遇到限流错误，可以增加延迟时间。

### 2. Token 消耗

每次测试大约消耗：
- 原版：~2000 tokens
- 增强版：~3500 tokens（提示词更长）

### 3. 错误处理

如果测试失败：
- 检查 API 密钥是否正确
- 检查网络连接
- 查看错误堆栈信息

---

## 🔄 测试流程

```
1. 读取测试文件
   ↓
2. 加载提示词
   ↓
3. 初始化 LLM 客户端
   ↓
4. 构建提示词（SYSTEM + USER）
   ↓
5. 调用 LLM
   ↓
6. 解析结果
   ↓
7. 统计过滤效果
   ↓
8. 对比两个版本
   ↓
9. 输出报告
```

---

## 💡 扩展测试

### 测试其他文件

修改 `TEST_FILE_PATH` 配置：

```python
TEST_FILE_PATH = r"C:\path\to\your\test.md"
```

### 测试其他模型

修改 `LLM_MODEL` 配置：

```python
LLM_MODEL = "gpt-4"  # 或其他模型
```

### 批量测试

可以扩展脚本支持多个测试文件��

```python
TEST_FILES = [
    r"path\to\test1.md",
    r"path\to\test2.md",
    r"path\to\test3.md",
]

for test_file in TEST_FILES:
    # 运行测试...
```

---

## 📞 问题反馈

如果遇到问题：
1. 查看控制台输出的错误信息
2. 检查配置是否正确填写
3. 确认测试文件和提示词文件路径正确

---

## ✅ 检查清单

测试前确认：
- [ ] 已填写 LLM_API_KEY
- [ ] 已填写 LLM_BASE_URL
- [ ] 已填写 LLM_MODEL（qwen-plus）
- [ ] 测试文件路径正确
- [ ] 提示词文件路径正确
- [ ] 网络连接正常

测试后检查：
- [ ] 两个版本都成功运行
- [ ] 查看对比结果
- [ ] 确认增强版过滤率提升
- [ ] 决定是否使用增强版提示词
