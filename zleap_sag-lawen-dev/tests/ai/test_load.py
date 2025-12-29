import nltk
from nltk.data import find
import logging

logger = logging.getLogger(__name__)

def download_nltk_resources(resources):
    """
    检查nltk资源是否存在，仅下载不存在的资源
    resources: 字典，key为资源名称，value为对应的查找路径
    """
    missing = []
    for name, path in resources.items():
        try:
            # 尝试查找资源，若存在则不做处理
            find(path)
            print(f"nltk资源 '{name}' 已存在，无需下载")
        except LookupError:
            # 资源不存在，加入待下载列表
            missing.append(name)
            print(f"nltk资源 '{name}' 不存在，需下载")
    
    if missing:
        print(f"开始下载缺失的nltk资源：{missing}")
        nltk.download(missing)
        print(f"nltk资源 {missing} 下载完成")
    else:
        print("所有nltk资源均已存在，无需下载")

# 定义需要检查的资源及其对应的查找路径
resource_paths = {
    "punkt": "tokenizers/punkt",   # punkt属于分词器（tokenizers）
    "punkt_tab": "tokenizers/punkt_tab"  # punkt_tab同样属于分词器
}

# 执行检查和下载
print("初始化nltk分词器环境")
download_nltk_resources(resource_paths)
print("nltk分词器环境准备完成")