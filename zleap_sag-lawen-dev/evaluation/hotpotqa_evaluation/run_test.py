"""
快速测试脚本

功能：
1. 测试完整的数据处理和评估流程（步骤1-4）
2. 处理少量样本（默认 3 个）
3. 验证输出文件

使用方法:
    python run_test.py              # 运行所有4个步骤
    python run_test.py --steps 1,2  # 只运行指定步骤
    python run_test.py --limit 5    # 使用5个样本进行测试
"""

import subprocess
import sys
import argparse
from pathlib import Path


def run_command(cmd, description):
    """运行命令并打印输出"""
    print(f"\n{'='*60}")
    print(f"🚀 {description}")
    print(f"{'='*60}")
    print(f"命令: {cmd}\n")

    result = subprocess.run(cmd, shell=True, capture_output=False, text=True)

    if result.returncode != 0:
        print(f"\n❌ 失败: {description}")
        return False

    print(f"\n✅ 完成: {description}")
    return True


def verify_files(data_dir: Path):
    """验证输出文件"""
    print(f"\n{'='*60}")
    print("📋 验证输出文件")
    print(f"{'='*60}")

    files_to_check = {
        "corpus.jsonl": "语料库文件",
        "corpus_merged.md": "语料库Markdown文件",
        "oracle.jsonl": "Oracle标准答案",
        "process_result.json": "处理结果",
        "test_search_results.json": "搜索结果",
        "ragas_evaluation_report.json": "RAGAs评估报告",
    }

    all_exist = True
    for filename, desc in files_to_check.items():
        filepath = data_dir / filename
        if filepath.exists():
            size = filepath.stat().st_size / 1024
            if filename.endswith('.jsonl'):
                lines = len(filepath.read_text(encoding='utf-8').strip().split('\n'))
                print(f"✅ {desc}: {lines} 行, {size:.2f} KB")
            else:
                print(f"✅ {desc}: {size:.2f} KB")
        else:
            print(f"❌ {desc} 不存在: {filename}")
            all_exist = False

    return all_exist


def main():
    parser = argparse.ArgumentParser(description='HotpotQA 评估流程测试')
    parser.add_argument('--limit', type=int, default=3,
                       help='测试样本数量（默认3）')
    parser.add_argument('--steps', type=str, default='1,2,3,4',
                       help='要运行的步骤，用逗号分隔（默认: 1,2,3,4）')
    parser.add_argument('--verbose', action='store_true',
                       help='显示详细日志')

    args = parser.parse_args()

    # 解析要运行的步骤
    steps_to_run = [int(s.strip()) for s in args.steps.split(',')]

    print("=" * 60)
    print("🧪 HotpotQA 评估流程测试")
    print("=" * 60)
    print(f"测试样本数: {args.limit}")
    print(f"运行步骤: {steps_to_run}")
    print()

    # 工作目录
    eval_dir = Path(__file__).parent
    scripts_dir = eval_dir / "scripts"
    data_dir = eval_dir / "data"

    print(f"📂 工作目录: {eval_dir}")
    print(f"📂 脚本目录: {scripts_dir}")
    print(f"📂 数据目录: {data_dir}\n")

    # 确保数据目录存在
    data_dir.mkdir(exist_ok=True)

    verbose_flag = " --verbose" if args.verbose else ""
    success = True

    # 步骤 1: 构建语料库
    if 1 in steps_to_run:
        success = run_command(
            f"python \"{scripts_dir}/1_build_corpus.py\" --limit {args.limit}",
            f"步骤 1: 构建语料库（{args.limit}个样本）"
        )
        if not success:
            sys.exit(1)

    # 步骤 2: 提取 Oracle
    if 2 in steps_to_run:
        success = run_command(
            f"python \"{scripts_dir}/2_extract_oracle.py\" --limit {args.limit}",
            f"步骤 2: 提取 Oracle（{args.limit}个样本）"
        )
        if not success:
            sys.exit(1)

    # 步骤 3: 上传语料库并测试搜索
    if 3 in steps_to_run:
        success = run_command(
            f"python \"{scripts_dir}/3_upload_corpus.py\" --test-queries{verbose_flag}",
            "步骤 3: 上传语料库并测试搜索"
        )
        if not success:
            sys.exit(1)

    # 步骤 4: RAGAs 评估
    if 4 in steps_to_run:
        success = run_command(
            f"python \"{scripts_dir}/4_ragas_evaluation.py\" --limit {args.limit}{verbose_flag}",
            f"步骤 4: RAGAs 评估（{args.limit}个问题）"
        )
        if not success:
            sys.exit(1)

    # 验证输出文件
    verify_files(data_dir)

    print(f"\n{'='*60}")
    print("🎉 测试完成！")
    print(f"{'='*60}")
    print("\n下一步:")
    print("  1. 查看数据目录中的各个文件")
    print(f"     cd {data_dir}")
    print("  2. 运行完整评估（所有样本）:")
    print(f"     python \"{scripts_dir}/1_build_corpus.py\"")
    print(f"     python \"{scripts_dir}/2_extract_oracle.py\"")
    print(f"     python \"{scripts_dir}/3_upload_corpus.py\" --test-queries")
    print(f"     python \"{scripts_dir}/4_ragas_evaluation.py\"")
    print("  3. 查看评估报告:")
    print(f"     {data_dir}/ragas_evaluation_report.json")
    print()


if __name__ == "__main__":
    main()
