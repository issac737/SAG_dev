"""
统一的 I/O 工具函数
"""
import json
from pathlib import Path
from typing import List, Type, TypeVar
from pydantic import BaseModel

T = TypeVar('T', bound=BaseModel)


def write_jsonl(data: List[BaseModel], output_path: Path):
    """
    写入 JSONL 文件（每行一个 JSON 对象）

    Args:
        data: Pydantic 模型列表
        output_path: 输出路径
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w', encoding='utf-8') as f:
        for item in data:
            f.write(item.model_dump_json() + '\n')

    print(f"[OK] 已保存 {len(data)} 条记录到: {output_path}")


def read_jsonl(input_path: Path, model_class: Type[T]) -> List[T]:
    """
    读取 JSONL 文件并验证数据格式

    Args:
        input_path: 输入路径
        model_class: Pydantic 模型类

    Returns:
        模型对象列表

    Raises:
        FileNotFoundError: 文件不存在
        ValidationError: 数据格式错误
    """
    input_path = Path(input_path)
    if not input_path.exists():
        raise FileNotFoundError(f"文件不存在: {input_path}")

    data = []
    with open(input_path, 'r', encoding='utf-8') as f:
        for i, line in enumerate(f, 1):
            if line.strip():
                try:
                    obj = model_class.model_validate_json(line)
                    data.append(obj)
                except Exception as e:
                    raise ValueError(f"第 {i} 行数据格式错误: {e}")

    print(f"[OK] 从 {input_path} 加载了 {len(data)} 条记录")
    return data


def write_json(data: BaseModel, output_path: Path):
    """写入单个 JSON 文件"""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(data.model_dump_json(indent=2))

    print(f"[OK] 已保存到: {output_path}")


def read_json(input_path: Path, model_class: Type[T]) -> T:
    """读取并验证单个 JSON 文件"""
    input_path = Path(input_path)
    if not input_path.exists():
        raise FileNotFoundError(f"文件不存在: {input_path}")

    with open(input_path, 'r', encoding='utf-8') as f:
        obj = model_class.model_validate_json(f.read())

    print(f"[OK] 从 {input_path} 加载数据")
    return obj
