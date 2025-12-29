"""
HotpotQA 评估配置文件

注意：数据集路径通过环境变量配置，请在项目根目录的 .env 文件中设置：
    HOTPOTQA_DATASET_PATH=/your/path/to/hotpotqa/dataset
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# 🔧 加载项目根目录的 .env 文件
project_root = Path(__file__).parent.parent.parent  # zleap_sag 根目录
env_path = project_root / ".env"
if env_path.exists():
    load_dotenv(env_path)
    print(f"✓ 已加载 .env 文件: {env_path}")
else:
    print(f"⚠️ 未找到 .env 文件: {env_path}")

# ============== 路径配置 ==============

# 基础目录
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"

# HotpotQA 数据集路径（从环境变量读取）
# 请在项目根目录的 .env 文件中配置 HOTPOTQA_DATASET_PATH
HOTPOTQA_DATASET_PATH = os.getenv("HOTPOTQA_DATASET_PATH", "")

# 输出文件路径
CORPUS_OUTPUT = DATA_DIR / "corpus.jsonl"
ORACLE_OUTPUT = DATA_DIR / "oracle.jsonl"

# ============== 数据集配置 ==============

# 使用的配置（distractor 或 fullwiki）
DATASET_CONFIG = "fullwiki"

# 使用的数据集分割（train 或 validation）
DATASET_SPLIT = "train"

# 样本数量限制（None 表示使用全部，用于测试时可以设置小的数字）
SAMPLE_LIMIT = None  # 或设置为 10, 100 等

# ============== 处理配置 ==============

# 是否启用去重
ENABLE_DEDUPLICATION = True

# 是否保存详细日志
VERBOSE = True

# 文本格式说明
# 使用 Markdown 格式：#{title}\n{content}
# 例如: "#Scott Derrickson\nScott Derrickson is..."
# 这样可以直接将 text 字段保存为 .md 文件

# ============== 验证配置 ==============

# 是否验证 chunk ID 存在性
VALIDATE_CHUNK_IDS = True

# 是否打印统计信息
PRINT_STATS = True
