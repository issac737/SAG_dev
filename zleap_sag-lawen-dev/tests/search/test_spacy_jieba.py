import re
import jieba
import spacy
import time  # 导入计时模块


"""

uv add spacy
uv pip install https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0.tar.gz
"""
# 加载spaCy英文模型
nlp_en = spacy.load("en_core_web_sm")

def optimized_mixed_segment(text):
    # 正则匹配非中文字符（英文、数字、符号等）
    pattern = re.compile(r'[^\u4e00-\u9fa5]+')
    matches = pattern.finditer(text)
    segments = []
    last_end = 0

    for match in matches:
        start, end = match.start(), match.end()
        # 处理中文部分
        if start > last_end:
            chinese_part = text[last_end:start]
            segments.extend(jieba.lcut(chinese_part))
        
        # 处理英文部分：用spaCy识别实体并合并
        english_part = text[start:end].strip()
        if english_part:
            print("加载成功")
            doc = nlp_en(english_part)
            current_pos = 0  # 记录当前处理到的位置
            for ent in doc.ents:
                # 实体前的非实体部分
                if ent.start_char > current_pos:
                    non_ent_text = english_part[current_pos:ent.start_char]
                    segments.extend([token.text for token in nlp_en(non_ent_text) if token.text.strip()])
                # 合并实体（如人名“Scott Derrickson”作为整体）
                segments.append(ent.text)
                current_pos = ent.end_char
            # 处理剩余非实体部分
            if current_pos < len(english_part):
                remaining_text = english_part[current_pos:]
                segments.extend([token.text for token in nlp_en(remaining_text) if token.text.strip()])
        
        last_end = end

    # 处理剩余中文
    if last_end < len(text):
        segments.extend(jieba.lcut(text[last_end:]))
    
    return [seg for seg in segments if seg.strip()]

# 测试案例
text = "Were Scott Derrickson and Ed Wood of the same nationality?"

# 统计耗时
start_time = time.perf_counter()  # 记录开始时间（高精度计时）



end_time = time.perf_counter()    # 记录结束时间

# 计算耗时（秒）
duration = end_time - start_time
# 测试文本：包含中文、英文单词、标点、数字、混合结构
test_texts = [
    "我喜欢用Python编程，也喜欢读《Deep Learning》这本书。",
    "2023年，AI领域的突破让GPT-4和BERT更加普及。",
    "Hello！这是一个中英文混合的test案例。",
    "他的邮箱是example@email.com，电话是123-4567-8901。",
    "Were Scott Derrickson and Ed Wood of the same nationality?"
]

for text in test_texts:
    print(f"原始文本：{text}")
    start_time = time.perf_counter()  # 记录开始时间（高精度计时）
    result = optimized_mixed_segment(text)
    end_time = time.perf_counter()    # 记录结束时间
# 输出结果和耗时
    print("分词结果:", result)
    print(f"分词耗时: {duration:.6f} 秒")  # 保留6位小数