#!/usr/bin/env python3
"""
Stage1 模块测试运行器

提供便捷的命令行界面来运行 Stage1 模块的各种测试
"""

import argparse
import asyncio
import sys
import os
import time
from pathlib import Path


def print_banner():
    """打印横幅"""
    print("""
╔══════════════════════════════════════════════════════════════╗
║                Stage1 模块测试工具                               ║
║                                                              ║
║  用于测试 8步骤复合搜索算法的完整性和性能                ║
╚══════════════════════════════════════════════════════════════╝
    """)


def print_help():
    """显示帮助信息"""
    print("""
🔧 使用方法:
  python run_stage1_tests.py [选项]

📋 可用选项:
  unit, u           - 运行单元测试
  integration, i    - 运行集成测试（需要完整环境）
  performance, p    - 运行性能测试
  complete, c       - 运行完整测试
  coverage, cov     - 生成覆盖率报告
  all, a           - 运行所有测试
  help, h           - 显示此帮助信息

💡 示例:
  python run_stage1_tests.py unit          # 只运行单元测试
  python run_stage1_tests.py integration    # 运行集成测试
  python run_stage1_tests.py coverage      # 生成覆盖率报告
  python run_stage1_tests.py all           # 运行所有测试

📊 测试类型说明:
  • 单元测试: 快速验证各个组件的逻辑正确性
  • 集成测试: 验证模块间的协作和端到端功能
  • 性能测试: 评估系统的性能指标
  • 完整测试: 包含模拟和真实环境的综合测试

📝 结果文件:
  测试结果会保存在 test_results/ 目录中
    """)


def run_unit_tests():
    """运行单元测试"""
    print("🧪 运行单元测试")
    print("-" * 40)

    try:
        import subprocess

        # 运行单元测试
        result = subprocess.run([
            sys.executable, "-m", "pytest",
            "test_stage1_complete.py::TestStage1UnitTests",
            "-v",
            "-s",
            "--tb=short"
        ], capture_output=True, text=True, cwd=Path(__file__).parent)

        print(result.stdout)
        if result.stderr:
            print("⚠️ 错误输出:")
            print(result.stderr)

        return result.returncode == 0

    except Exception as e:
        print(f"❌ 单元测试运行失败: {e}")
        return False


def run_integration_tests():
    """运行集成测试"""
    print("🔗 运行集成测试")
    print("-" * 40)

    try:
        import subprocess

        # 运行集成测试
        result = subprocess.run([
            sys.executable, "-m", "pytest",
            "test_stage1_complete.py::TestStage1IntegrationTests",
            "-v",
            "-s",
            "--tb=short",
            "-m", "integration"
        ], capture_output=True, text=True, cwd=Path(__file__).parent)

        print(result.stdout)
        if result.stderr:
            print("⚠️ 错误输出:")
            print(result.stderr)

        return result.returncode == 0

    except Exception as e:
        print(f"❌ 集成测试运行失败: {e}")
        return False


def run_performance_tests():
    """运行性能测试"""
    print("⚡ 运行性能测试")
    print("-" * 40)

    try:
        import subprocess

        # 运行性能测试
        result = subprocess.run([
            sys.executable, "-m", "pytest",
            "test_stage1_complete.py::TestStage1PerformanceTests",
            "-v",
            "-s",
            "--tb=short",
            "-m", "slow"
        ], capture_output=True, text=True, cwd=Path(__file__).parent)

        print(result.stdout)
        if result.stderr:
            print("⚠️ 错误输出:")
            print(result.stderr)

        return result.returncode == 0

    except Exception as e:
        print(f"❌ 性能测试运行失败: {e}")
        return False


def run_complete_tests():
    """运行完整测试"""
    print("🔬 运行完整测试")
    print("-" * 40)

    try:
        # 切换到测试目录
        test_dir = Path(__file__).parent
        os.chdir(test_dir)

        # 运行完整测试脚本
        result = subprocess.run([
            sys.executable, "test_stage1_complete.py",
            "--integration"
        ], capture_output=True, text=True)

        print(result.stdout)
        if result.stderr:
            print("⚠️ 错误输出:")
            print(result.stderr)

        return result.returncode == 0

    except Exception as e:
        print(f"❌ 完整测试运行失败: {e}")
        return False


def run_coverage_report():
    """生成覆盖率报告"""
    print("📊 生成覆盖率报告")
    print("-" * 40)

    try:
        import subprocess

        # 生成HTML覆盖率报告
        result = subprocess.run([
            sys.executable, "-m", "pytest",
            "test_stage1_complete.py",
            "--cov=dataflow.modules.search",
            "--cov-report=html",
            "--cov-report=term",
            "--cov-fail-under=80"
        ], capture_output=True, text=True, cwd=Path(__file__).parent)

        print(result.stdout)
        if result.stderr:
            print("⚠️ 错误输出:")
            print(result.stderr)

        if result.returncode == 0:
            print("✅ 覆盖率报告已生成")
            print("📁 查看报告: htmlcov/index.html")

        return result.returncode == 0

    except Exception as e:
        print(f"❌ 生成覆盖率报告失败: {e}")
        return False


def run_all_tests():
    """运行所有测试"""
    print("🚀 运行所有测试")
    print("=" * 50)

    tests = [
        ("单元测试", run_unit_tests),
        ("集成测试", run_integration_tests),
        ("覆盖率报告", run_coverage_report)
    ]

    results = []

    for test_name, test_func in tests:
        print(f"\n📋 {test_name}")
        try:
            success = test_func()
            results.append((test_name, success))
            status = "✅" if success else "❌"
            print(f"{status} {test_name}")
        except Exception as e:
            print(f"❌ {test_name}: {e}")
            results.append((test_name, False))

    # 总结
    print("\n" + "=" * 50)
    print("📈 测试总结")
    print("=" * 50)

    successful = sum(1 for _, success in results if success)
    total = len(results)

    for test_name, success in results:
        status = "✅" if success else "❌"
        print(f"{status} {test_name}")

    print(f"\n总体结果: {successful}/{total} 测试通过")

    if successful == total:
        print("🎉 所有测试都通过了！")
    else:
        print(f"⚠️ 有 {total - successful} 个测试失败，请检查上述错误信息")

    return successful == total


def check_environment():
    """检查测试环境并提供详细诊断"""
    print("🔍 检查测试环境")
    print("-" * 30)

    diagnostic_info = {}
    issues = []

    # 1. 检查Python版本和路径
    python_version = sys.version_info
    diagnostic_info["python"] = {
        "version": f"{python_version.major}.{python_version.minor}.{python_version.micro}",
        "executable": sys.executable,
        "path": sys.path[:3]  # 只显示前3个路径
    }

    if python_version < (3, 8):
        issues.append(f"Python版本过低: {python_version.major}.{python_version.minor}, 需要3.8+")

    # 2. 检查虚拟环境
    in_venv = (
        hasattr(sys, 'real_prefix') or  # venv
        hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix or  # venv
        'CONDA_DEFAULT_ENV' in os.environ or  # conda
        os.path.exists(os.path.join(sys.prefix, 'pyvenv.cfg'))  # pyvenv
    )
    diagnostic_info["virtual_env"] = {
        "in_virtual_env": in_venv,
        "prefix": sys.prefix,
        "base_prefix": getattr(sys, 'base_prefix', None)
    }

    # 3. 检查必要的包（使用多种方法）
    required_packages = [
        "pytest",
        "pytest_asyncio",  # 正确的包名
        "sqlalchemy",
        "aiofiles"
    ]

    package_check_results = {}
    for package in required_packages:
        check_result = check_package_detailed(package)
        package_check_results[package] = check_result

        if not check_result["available"]:
            issues.append(f"缺少包: {package} ({check_result.get('error', 'unknown error')})")

    diagnostic_info["packages"] = package_check_results

    # 4. 检查测试文件
    test_file = Path(__file__).parent / "test_stage1_complete.py"
    diagnostic_info["test_files"] = {
        "main_test": test_file.exists(),
        "main_test_path": str(test_file)
    }

    if not test_file.exists():
        issues.append(f"测试文件不存在: {test_file}")

    # 5. 检查当前工作目录
    current_dir = Path.cwd()
    expected_dir = Path(__file__).parent
    diagnostic_info["directory"] = {
        "current": str(current_dir),
        "expected": str(expected_dir),
        "correct": current_dir == expected_dir
    }

    if current_dir != expected_dir:
        issues.append(f"工作目录不正确，应该在 {expected_dir}")

    # 显示诊断结果
    if issues:
        print("❌ 发现环境问题:")
        for issue in issues:
            print(f"  • {issue}")

        print("\n🔍 详细诊断信息:")
        print_diagnostic_info(diagnostic_info)

        print("\n💡 修复建议:")
        print_environment_fix_suggestions(diagnostic_info, issues)

        return False
    else:
        print("✅ 环境检查通过")
        print_diagnostic_info(diagnostic_info)
        return True


def check_package_detailed(package_name):
    """详细检查包的可用性"""
    import importlib.util

    result = {
        "available": False,
        "method": None,
        "version": None,
        "error": None
    }

    # 方法1: 使用 importlib 检查
    try:
        spec = importlib.util.find_spec(package_name)
        if spec is not None:
            result["available"] = True
            result["method"] = "importlib"

            # 尝试获取版本
            try:
                module = importlib.util.module_from_spec(spec)
                if hasattr(module, '__version__'):
                    result["version"] = module.__version__
                elif hasattr(module, '__version_info__'):
                    result["version"] = ".".join(map(str, module.__version_info__))
            except:
                pass

            return result
    except Exception as e:
        result["error"] = f"importlib检查失败: {e}"

    # 方法2: 尝试直接导入（兼容性检查）
    try:
        __import__(package_name)
        result["available"] = True
        result["method"] = "direct_import"
        return result
    except ImportError as e:
        if result["error"] is None:
            result["error"] = f"导入失败: {e}"

    # 方法3: 使用 subprocess 检查（最后手段）
    try:
        import subprocess
        cmd = [sys.executable, "-c", f"import {package_name}; print('OK')"]
        result_obj = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result_obj.returncode == 0 and "OK" in result_obj.stdout:
            result["available"] = True
            result["method"] = "subprocess"
            return result
    except Exception as e:
        if result["error"] is None:
            result["error"] = f"subprocess检查失败: {e}"

    return result


def print_diagnostic_info(info):
    """打印诊断信息"""
    print(f"\n📋 Python信息:")
    print(f"  版本: {info['python']['version']}")
    print(f"  路径: {info['python']['executable']}")
    print(f"  前几个sys.path: {info['python']['path']}")

    print(f"\n🐍 虚拟环境:")
    print(f"  在虚拟环境中: {'是' if info['virtual_env']['in_virtual_env'] else '否'}")
    print(f"  前缀: {info['virtual_env']['prefix']}")

    print(f"\n📦 包检查结果:")
    for package, check_result in info['packages'].items():
        status = "✅" if check_result['available'] else "❌"
        method = check_result['method']
        version = f" (v{check_result['version']})" if check_result['version'] else ""
        error = f" - {check_result['error']}" if check_result['error'] else ""
        print(f"  {status} {package} [{method}]{version}{error}")

    print(f"\n📁 测试文件:")
    print(f"  主测试文件: {'存在' if info['test_files']['main_test'] else '不存在'}")
    print(f"  路径: {info['test_files']['main_test_path']}")

    print(f"\n📂 工作目录:")
    print(f"  当前: {info['directory']['current']}")
    print(f"  期望: {info['directory']['expected']}")
    print(f"  正确: {'是' if info['directory']['correct'] else '否'}")


def print_environment_fix_suggestions(info, issues):
    """打印环境修复建议"""
    suggestions = []

    # 基于具体问题提供建议
    for issue in issues:
        if "pytest-asyncio" in issue:
            suggestions.append("安装 pytest-asyncio: pip install pytest-asyncio")
        elif "pytest" in issue:
            suggestions.append("安装 pytest: pip install pytest")
        elif "aiofiles" in issue:
            suggestions.append("安装 aiofiles: pip install aiofiles")
        elif "sqlalchemy" in issue:
            suggestions.append("安装 sqlalchemy: pip install sqlalchemy")
        elif "工作目录不正确" in issue:
            suggestions.append(f"切换到正确目录: cd {info['directory']['expected']}")
        elif "Python版本过低" in issue:
            suggestions.append("升级 Python 到 3.8+ 版本")

    # 通用建议
    if not info['virtual_env']['in_virtual_env']:
        suggestions.append("建议使用虚拟环境来隔离依赖")

    if info['python']['executable'].startswith('/usr/bin/'):
        suggestions.append("建议使用虚拟环境中的Python解释器")

    # 去重建议
    unique_suggestions = list(set(suggestions))
    for suggestion in unique_suggestions:
        print(f"  • {suggestion}")

    # 自动修复选项
    print(f"\n🔧 自动修复选项:")
    print(f"  python {__file__} --fix-env")
    print(f"  # 这将尝试自动修复常见的环境问题")


def fix_environment():
    """自动修复环境问题"""
    print("🔧 尝试自动修复环境问题")
    print("-" * 40)

    success = True
    fixes_applied = []

    # 1. 修复工作目录
    current_dir = Path.cwd()
    expected_dir = Path(__file__).parent
    if current_dir != expected_dir:
        try:
            os.chdir(expected_dir)
            fixes_applied.append(f"切换到正确目录: {expected_dir}")
            print(f"✅ 修复工作目录: {expected_dir}")
        except Exception as e:
            print(f"❌ 修复工作目录失败: {e}")
            success = False

    # 2. 尝试安装缺失的包
    required_packages = {
        "pytest": ["pytest"],
        "pytest-asyncio": ["pytest-asyncio"],  # 修正包名
        "aiofiles": ["aiofiles"],
        "sqlalchemy": ["sqlalchemy"]
    }

    for package, pip_names in required_packages.items():
        package_result = check_package_detailed(package)
        if not package_result["available"]:
            print(f"📦 尝试安装 {package}...")
            for pip_name in pip_names:
                try:
                    import subprocess
                    result = subprocess.run(
                        [sys.executable, "-m", "pip", "install", pip_name],
                        capture_output=True,
                        text=True,
                        timeout=120
                    )
                    if result.returncode == 0:
                        fixes_applied.append(f"安装 {package}")
                        print(f"✅ 成功安装 {package}")
                        break
                    else:
                        print(f"⚠️  pip install {pip_name} 失败: {result.stderr.strip()}")
                except Exception as e:
                    print(f"❌ 安装 {package} 失败: {e}")
            # 检查安装是否成功
            time.sleep(1)
            package_result = check_package_detailed(package)
            if not package_result["available"]:
                print(f"❌ {package} 安装后仍然不可用")
                success = False

    # 3. 验证修复结果
    print("\n🔍 验证修复结果")
    if check_environment():
        print("✅ 环境修复成功！")
        print(f"应用的修复: {len(fixes_applied)}")
        return True
    else:
        print("❌ 环境修复失败，请手动检查以下问题:")
        # 重新运行检查以获取最新状态
        check_environment()
        return False


def run_lightweight_tests():
    """运行轻量级测试（最小依赖）"""
    print("🪶 运行轻量级测试")
    print("-" * 40)

    try:
        # 只测试核心逻辑，不需要外部依赖
        print("📋 测试1: Python 基础功能")
        basic_tests = []

        # 测试数据结构
        try:
            from dataflow.modules.search.stage1 import Stage1Result
            result = Stage1Result(
                key_final=[{"key": "test", "weight": 0.8, "steps": [1]}],
                key_query_related=[],
                event_key_query_related=[],
                event_query_related=[],
                event_related=[],
                key_related=[],
                event_key_weights={},
                event_key_query_weights={},
                key_event_weights={}
            )

            # 测试JSON序列化
            import json
            json_str = json.dumps(result.__dict__)
            basic_tests.append(("Stage1Result序列化", True, None))

        except Exception as e:
            basic_tests.append(("Stage1Result序列化", False, str(e)))

        # 测试配置类
        try:
            from dataflow.modules.search.config import Stage1SearchConfig
            config = Stage1SearchConfig(
                source_config_id="test",
                query="test query"
            )
            basic_tests.append(("SearchConfig创建", True, None))
        except Exception as e:
            basic_tests.append(("SearchConfig创建", False, str(e)))

        # 测试日志功能
        try:
            from dataflow.utils import get_logger
            test_logger = get_logger("test.stage1_lightweight")
            test_logger.info("轻量级测试日志")
            basic_tests.append(("日志功能", True, None))
        except Exception as e:
            basic_tests.append(("日志功能", False, str(e)))

        # 显示结果
        print("\n📊 测试结果:")
        passed = 0
        for test_name, success, error in basic_tests:
            status = "✅" if success else "❌"
            print(f"  {status} {test_name}")
            if not success:
                print(f"    错误: {error}")
            else:
                passed += 1

        print(f"\n📈 轻量级测试结果: {passed}/{len(basic_tests)} 通过")

        return passed == len(basic_tests)

    except Exception as e:
        print(f"❌ 轻量级测试失败: {e}")
        return False


def main():
    """主函数"""
    print_banner()

    if len(sys.argv) < 2:
        print_help()
        return

    command = sys.argv[1].lower()

    # 特殊命令：环境修复
    if command in ['fix-env', 'fix']:
        success = fix_environment()
        sys.exit(0 if success else 1)

    # 常规测试命令
    if command in ['unit', 'u']:
        if check_environment():
            success = run_unit_tests()
            sys.exit(0 if success else 1)
        else:
            print("❌ 环境检查失败，请先修复环境")
            print("💡 尝试: python run_stage1_tests.py fix-env")
            sys.exit(1)

    elif command in ['integration', 'i']:
        if check_environment():
            success = run_integration_tests()
            sys.exit(0 if success else 1)
        else:
            print("❌ 环境检查失败，请先修复环境")
            print("💡 尝试: python run_stage1_tests.py fix-env")
            sys.exit(1)

    elif command in ['performance', 'p']:
        if check_environment():
            success = run_performance_tests()
            sys.exit(0 if success else 1)
        else:
            print("❌ 环境检查失败，请先修复环境")
            print("💡 尝试: python run_stage1_tests.py fix-env")
            sys.exit(1)

    elif command in ['complete', 'c']:
        if check_environment():
            success = run_complete_tests()
            sys.exit(0 if success else 1)
        else:
            print("❌ 环境检查失败，请先修复环境")
            print("💡 尝试: python run_stage1_tests.py fix-env")
            sys.exit(1)

    elif command in ['coverage', 'cov']:
        if check_environment():
            success = run_coverage_report()
            sys.exit(0 if success else 1)
        else:
            print("❌ 环境检查失败，请先修复环境")
            print("💡 尝试: python run_stage1_tests.py fix-env")
            sys.exit(1)

    elif command in ['all', 'a']:
        if check_environment():
            success = run_all_tests()
            sys.exit(0 if success else 1)
        else:
            print("❌ 环境检查失败，请先修复环境")
            print("💡 尝试: python run_stage1_tests.py fix-env")
            sys.exit(1)

    elif command in ['lightweight', 'light', 'l']:
        # 轻量级测试不需要环境检查
        success = run_lightweight_tests()
        sys.exit(0 if success else 1)

    elif command in ['help', 'h', '-h', '--help']:
        print_help()
        # 添加额外帮助信息
        print("\n🔧 环境修复:")
        print("  python run_stage1_tests.py fix-env")
        print("\n🪶 轻量级测试:")
        print("  python run_stage1_tests.py lightweight")
        print("  # 无需外部依赖，只测试核心逻辑")

    elif command in ['diagnose', 'diag', 'd']:
        # 只进行环境诊断，不运行测试
        print("🔧 仅进行环境诊断")
        check_environment()

    else:
        print(f"❌ 未知命令: {command}")
        print("💡 使用 'python run_stage1_tests.py help' 查看帮助")
        print("\n💡 可用命令包括:")
        print("  unit, integration, performance, complete, coverage, all")
        print("  lightweight, fix-env, diagnose, help")
        sys.exit(1)


if __name__ == "__main__":
    main()