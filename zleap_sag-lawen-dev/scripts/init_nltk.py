"""
NLTK 数据初始化脚本

用于本地开发时一键下载所有需要的 NLTK 数据资源
避免首次启动时下载失败或数据损坏的问题
"""

import sys
import ssl
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dataflow.utils import get_logger

logger = get_logger("scripts.init_nltk")

def init_nltk_data():
    """初始化 NLTK 数据"""
    try:
        import nltk
        
        # 处理 SSL 证书问题
        try:
            _create_unverified_https_context = ssl._create_unverified_context
        except AttributeError:
            pass
        else:
            ssl._create_default_https_context = _create_unverified_https_context
        
        logger.info("开始检查和下载 NLTK 数据资源...")
        
        # 需要的资源列表
        required_resources = {
            'punkt': 'tokenizers/punkt',
            'punkt_tab': 'tokenizers/punkt_tab'
        }
        
        downloaded = []
        skipped = []
        
        for resource_name, resource_path in required_resources.items():
            try:
                # 检查资源是否已存在
                nltk.data.find(resource_path)
                logger.info(f"✓ {resource_name} 已存在，跳过下载")
                skipped.append(resource_name)
            except LookupError:
                # 资源不存在，需要下载
                logger.info(f"✗ {resource_name} 不存在，开始下载...")
                try:
                    nltk.download(resource_name, quiet=False)
                    logger.info(f"✓ {resource_name} 下载成功")
                    downloaded.append(resource_name)
                except Exception as e:
                    logger.error(f"✗ {resource_name} 下载失败: {e}")
                    raise
        
        # 验证所有资源
        logger.info("\n验证 NLTK 数据...")
        all_ok = True
        for resource_name, resource_path in required_resources.items():
            try:
                path = nltk.data.find(resource_path)
                logger.info(f"✓ {resource_name}: {path}")
            except Exception as e:
                logger.error(f"✗ {resource_name} 验证失败: {e}")
                all_ok = False
        
        # 总结
        print("\n" + "="*60)
        print("NLTK 数据初始化完成！")
        print("="*60)
        if downloaded:
            print(f"已下载: {', '.join(downloaded)}")
        if skipped:
            print(f"已存在: {', '.join(skipped)}")
        if all_ok:
            print("\n✅ 所有资源验证通过，可以正常使用！")
        else:
            print("\n⚠️ 部分资源验证失败，请检查日志")
        print("="*60)
        
        return all_ok
        
    except Exception as e:
        logger.error(f"NLTK 数据初始化失败: {e}")
        print(f"\n❌ 初始化失败: {e}")
        print("\n尝试手动修复:")
        print("  1. 删除损坏的数据: rm -rf ~/nltk_data/tokenizers/punkt*")
        print("  2. 重新运行此脚本: python scripts/init_nltk.py")
        return False

if __name__ == "__main__":
    print("="*60)
    print("DataFlow - NLTK 数据初始化工具")
    print("="*60)
    print()
    
    success = init_nltk_data()
    sys.exit(0 if success else 1)

