"""
分词器与关键词提取模块

提供：
1. 中英文混合分词（MixedTokenizer）
2. 关键词提取（KeywordExtractor）- 支持 tokenizer / llm / merge 三种模式

使用示例：
    # 分词
    >>> from dataflow.core.ai.tokensize import tokenize
    >>> tokens = tokenize("我喜欢Python编程")
    ['我', '喜欢', 'Python', '编程']
    
    # 关键词提取
    >>> from dataflow.core.ai.tokensize import extract_keywords, POS
    >>> keywords = extract_keywords("苹果公司发布新款iPhone")
    ['苹果公司', 'iPhone']
    
    >>> keywords = await extract_keywords_async("文本", mode="llm")
"""

import re
import threading
from enum import Enum
from typing import List, Optional, Set, Tuple

from dataflow.utils import get_logger

logger = get_logger("ai.tokenizer")


# ==================== 词性枚举（统一抽象） ====================


class POS(str, Enum):
    """
    统一词性标签
    
    内部自动映射到：
    - jieba: n, nr, ns, nt, nz, v, vn, a, d
    - spaCy: NOUN, PROPN, VERB, ADJ, ADV + NER 实体类型
    - LLM: 自然语言描述
    """
    # 名词类
    NOUN = "noun"           # 普通名词
    PERSON = "person"       # 人名
    PLACE = "place"         # 地名
    ORG = "org"             # 机构名
    PRODUCT = "product"     # 产品名/品牌名
    
    # 动词类
    VERB = "verb"           # 动词
    
    # 其他
    ADJ = "adj"             # 形容词
    ADV = "adv"             # 副词


# 词性映射：POS -> jieba 词性标签
_JIEBA_POS_MAP = {
    POS.NOUN: ("n", "nz"),
    POS.PERSON: ("nr",),
    POS.PLACE: ("ns",),
    POS.ORG: ("nt",),
    POS.PRODUCT: ("nz",),
    POS.VERB: ("v", "vn"),
    POS.ADJ: ("a",),
    POS.ADV: ("d",),
}

# 词性映射：POS -> spaCy 词性标签
_SPACY_POS_MAP = {
    POS.NOUN: ("NOUN",),
    POS.PERSON: ("PROPN",),
    POS.PLACE: ("PROPN",),
    POS.ORG: ("PROPN",),
    POS.PRODUCT: ("PROPN",),
    POS.VERB: ("VERB",),
    POS.ADJ: ("ADJ",),
    POS.ADV: ("ADV",),
}

# 词性映射：POS -> spaCy NER 实体类型
_SPACY_ENTITY_MAP = {
    POS.PERSON: ("PERSON",),
    POS.PLACE: ("GPE", "LOC"),
    POS.ORG: ("ORG",),
    POS.PRODUCT: ("PRODUCT", "WORK_OF_ART"),
}

# 词性映射：POS -> LLM 自然语言描述
_LLM_POS_DESC = {
    POS.NOUN: "普通名词",
    POS.PERSON: "人名",
    POS.PLACE: "地名",
    POS.ORG: "机构名、组织名、公司名",
    POS.PRODUCT: "产品名、品牌名",
    POS.VERB: "动词",
    POS.ADJ: "形容词",
    POS.ADV: "副词",
}


# 默认词性：只要名词类（使用 frozenset 防止意外修改）
DEFAULT_POS: frozenset = frozenset({POS.NOUN, POS.PERSON, POS.PLACE, POS.ORG, POS.PRODUCT})


# ==================== 停用词 ====================


CHINESE_STOPWORDS: frozenset = frozenset({
    # 代词
    "我", "你", "他", "她", "它", "我们", "你们", "他们", "自己", "什么", "哪", "哪里",
    # 助词
    "的", "地", "得", "了", "着", "过", "啊", "呢", "吧", "啦", "呀",
    # 连词
    "和", "与", "及", "或", "而", "但", "但是", "然而", "虽然", "因为", "所以", "如果",
    # 介词
    "在", "从", "向", "到", "对", "于", "为", "以", "把", "被", "让", "给",
    # 副词
    "很", "非常", "太", "更", "最", "都", "也", "就", "才", "只", "还", "又", "再",
    # 动词（高频无意义）
    "是", "有", "做", "去", "来", "说", "要", "会", "能", "可以", "应该", "需要",
    # 数量词
    "一", "二", "三", "个", "些", "点", "这", "那", "这个", "那个", "这些", "那些",
    # 其他
    "等", "等等", "就是", "可能", "已经", "正在", "没有", "不", "没",
})

ENGLISH_STOPWORDS: frozenset = frozenset({
    "a", "an", "the", "i", "you", "he", "she", "it", "we", "they", "me", "him", "her",
    "us", "them", "my", "your", "his", "its", "our", "their", "this", "that", "these",
    "those", "who", "whom", "what", "which", "whose", "where", "when", "why", "how",
    "in", "on", "at", "to", "for", "of", "with", "by", "from", "into", "through",
    "during", "before", "after", "above", "below", "between", "under", "about",
    "and", "but", "or", "nor", "so", "yet", "both", "either", "neither", "if", "then",
    "is", "are", "was", "were", "be", "been", "being", "have", "has", "had",
    "do", "does", "did", "will", "would", "could", "should", "may", "might", "must", "can",
    "not", "no", "only", "just", "also", "very", "too", "more", "most", "than",
    "as", "such", "some", "any", "all", "each", "every", "other", "another",
})

DEFAULT_STOPWORDS: frozenset = CHINESE_STOPWORDS | ENGLISH_STOPWORDS


# ==================== MixedTokenizer ====================


class MixedTokenizer:
    """
    中英文混合分词器（单例模式）

    特点：
    - 中文使用 jieba 分词
    - 英文使用 spaCy 分词，识别并保留实体完整性（如人名）
    - 懒加载：首次调用时才加载 spaCy 模型
    - 单例模式：全局只加载一次 spaCy 模型，避免重复加载耗时
    - 线程安全：使用双重检查锁定模式

    使用示例：
        tokenizer = MixedTokenizer.get_instance()
        tokens = tokenizer.tokenize("我喜欢用Python编程")
    """

    _instance = None
    _lock = threading.Lock()

    def __init__(self):
        """
        私有构造函数，防止外部直接实例化

        注意：不要直接调用此方法，请使用 get_instance() 获取单例
        """
        self._nlp_en = None
        self._spacy_loaded = False
        self._spacy_failed = False
        logger.info("MixedTokenizer 实例已创建（spaCy 模型尚未加载，将在首次使用时懒加载）")

    @classmethod
    def get_instance(cls):
        """
        获取 MixedTokenizer 单例实例

        使用双重检查锁定（Double-Checked Locking）确保线程安全

        Returns:
            MixedTokenizer: 全局唯一的分词器实例
        """
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def _load_spacy_model(self):
        """
        懒加载 spaCy 英文模型

        只在首次调用 tokenize() 时加载，避免启动时的性能损耗
        """
        if self._spacy_loaded or self._spacy_failed:
            return

        with self._lock:
            # 双重检查
            if self._spacy_loaded or self._spacy_failed:
                return

            try:
                import spacy

                logger.info("正在加载 spaCy 英文模型（en_core_web_sm）...")
                self._nlp_en = spacy.load("en_core_web_sm")
                self._spacy_loaded = True
                logger.info("✅ spaCy 英文模型加载成功")
            except Exception as e:
                self._spacy_failed = True
                logger.warning(
                    f"⚠️ spaCy 英文模型加载失败，将使用降级分词方案: {e}\n"
                    f"提示：安装 spaCy 模型以获得更好的分词效果：\n"
                    f"  uv add spacy\n"
                    f"  uv pip install https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0.tar.gz"
                )

    def tokenize(self, text: str, fast_mode: bool = False) -> List[str]:
        """
        对文本进行中英文混合分词

        处理流程：
        1. 使用正则表达式分离中文和非中文部分
        2. 中文部分使用 jieba 分词
        3. 英文部分：
           - fast_mode=False: 使用 spaCy 分词（识别实体），若不可用则降级到空格分词
           - fast_mode=True: 直接使用空格分词（更快）
        4. 过滤空白字符

        Args:
            text: 待分词的文本
            fast_mode: 快速模式，跳过 spaCy 分词，只使用 jieba + 空格分词（默认False）

        Returns:
            List[str]: 分词结果列表

        示例：
            >>> tokenizer = MixedTokenizer.get_instance()
            >>> tokenizer.tokenize("我喜欢用Python编程")
            ['我', '喜欢', '用', 'Python', '编程']
            >>> tokenizer.tokenize("Were Scott Derrickson and Ed Wood of the same nationality?")
            ['Were', 'Scott Derrickson', 'and', 'Ed Wood', 'of', 'the', 'same', 'nationality', '?']
            >>> tokenizer.tokenize("我喜欢用Python编程", fast_mode=True)  # 快速模式
            ['我', '喜欢', '用', 'Python', '编程']
        """
        # 懒加载 spaCy 模型（仅在非快速模式下）
        if not fast_mode and not self._spacy_loaded and not self._spacy_failed:
            self._load_spacy_model()

        # 正则匹配非中文字符（英文、数字、符号等）
        pattern = re.compile(r"[^\u4e00-\u9fa5]+")
        matches = pattern.finditer(text)
        segments = []
        last_end = 0

        for match in matches:
            start, end = match.start(), match.end()

            # 处理中文部分
            if start > last_end:
                chinese_part = text[last_end:start]
                try:
                    import jieba
                    segments.extend(jieba.lcut(chinese_part))
                except ImportError:
                    # jieba未安装，使用简单分词
                    segments.extend(chinese_part.split())

            # 处理英文部分
            english_part = text[start:end].strip()
            if english_part:
                if fast_mode:
                    # 快速模式：直接空格分词
                    segments.extend(self._tokenize_english_simple(english_part))
                elif self._spacy_loaded and self._nlp_en is not None:
                    # 使用 spaCy 识别实体并合并
                    segments.extend(self._tokenize_english_with_spacy(english_part))
                else:
                    # 降级方案：简单的空格分词
                    segments.extend(self._tokenize_english_simple(english_part))

            last_end = end

        # 处理剩余中文
        if last_end < len(text):
            try:
                import jieba
                segments.extend(jieba.lcut(text[last_end:]))
            except ImportError:
                # jieba未安装，使用简单分词
                segments.extend(text[last_end:].split())

        # 过滤空白
        return [seg for seg in segments if seg.strip()]

    def _tokenize_english_with_spacy(self, text: str) -> List[str]:
        """
        使用 spaCy 对英文文本分词，识别并保留实体完整性

        Args:
            text: 英文文本

        Returns:
            List[str]: 分词结果
        """
        doc = self._nlp_en(text)
        segments = []
        current_pos = 0

        for ent in doc.ents:
            # 实体前的非实体部分
            if ent.start_char > current_pos:
                non_ent_text = text[current_pos : ent.start_char]
                segments.extend(
                    [token.text for token in self._nlp_en(non_ent_text) if token.text.strip()]
                )
            # 合并实体（如人名"Scott Derrickson"作为整体）
            segments.append(ent.text)
            current_pos = ent.end_char

        # 处理剩余非实体部分
        if current_pos < len(text):
            remaining_text = text[current_pos:]
            segments.extend(
                [token.text for token in self._nlp_en(remaining_text) if token.text.strip()]
            )

        return segments

    def _tokenize_english_simple(self, text: str) -> List[str]:
        """
        简单的英文分词（降级方案）

        Args:
            text: 英文文本

        Returns:
            List[str]: 分词结果
        """
        return [word for word in text.split() if word.strip()]

    @property
    def is_spacy_available(self) -> bool:
        """
        检查 spaCy 是否可用

        Returns:
            bool: True 表示 spaCy 已成功加载，False 表示使用降级方案
        """
        return self._spacy_loaded
    
    def get_spacy_nlp(self):
        """
        获取 spaCy NLP 模型（懒加载）
        
        Returns:
            spacy.Language 或 None（加载失败时）
        """
        self._load_spacy_model()
        return self._nlp_en


# ==================== KeywordExtractor ====================


class KeywordExtractor:
    """
    关键词提取器
    
    支持三种模式：
    - tokenizer: 分词器提取（快速，离线，默认）
    - llm: LLM提取（精准，需要API）
    - merge: 合并模式（分词器 + LLM 去重合并）
    
    配置优先级：方法参数 > 实例配置 > 全局默认值
    
    Example:
        >>> extractor = KeywordExtractor()
        >>> 
        >>> # 默认全部提取（名词类）
        >>> keywords = extractor.extract("苹果公司发布了新款iPhone")
        ['苹果公司', 'iPhone', '新款']
        >>> 
        >>> # 限制数量
        >>> keywords = extractor.extract("文本", top_k=5)
        >>> 
        >>> # 临时指定词性
        >>> keywords = extractor.extract("文本", pos={POS.NOUN, POS.VERB})
    """
    
    _instance = None
    _lock = threading.Lock()
    _jieba_lock = threading.Lock()
    
    def __init__(
        self,
        pos: Optional[Set[POS]] = None,
        stopwords: Optional[Set[str]] = None,
        min_len: int = 2,
    ):
        """
        初始化
        
        Args:
            pos: 词性过滤，None 使用默认（只要名词类）
            stopwords: 停用词，None 使用内置默认
            min_len: 最小关键词长度（过滤单字）
        """
        self.default_pos: Set[POS] = set(pos) if pos is not None else set(DEFAULT_POS)
        self.default_stopwords: Set[str] = set(stopwords) if stopwords is not None else set(DEFAULT_STOPWORDS)
        self.min_len = min_len
        self._jieba_initialized = False
    
    @classmethod
    def get_instance(cls) -> "KeywordExtractor":
        """获取单例（使用默认配置）"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance
    
    # ==================== 公开接口 ====================
    
    def extract(
        self,
        text: str,
        top_k: Optional[int] = None,
        mode: str = "tokenizer",
        pos: Optional[Set[POS]] = None,
        stopwords: Optional[Set[str]] = None,
    ) -> List[str]:
        """
        同步提取关键词（仅 tokenizer 模式）
        
        Args:
            text: 输入文本
            top_k: 返回前K个，None 表示全部
            mode: 模式（同步只支持 tokenizer）
            pos: 词性过滤（临时覆盖），None 使用实例配置
            stopwords: 停用词（临时覆盖），None 使用实例配置
        
        Returns:
            关键词列表，无匹配返回 []
        """
        if mode != "tokenizer":
            logger.warning(f"同步方法只支持 tokenizer，当前: {mode}，已自动切换")
        
        effective_pos = pos if pos is not None else self.default_pos
        effective_stopwords = stopwords if stopwords is not None else self.default_stopwords
        
        return self._extract_by_tokenizer(text, top_k, effective_pos, effective_stopwords)
    
    async def extract_async(
        self,
        text: str,
        top_k: Optional[int] = None,
        mode: str = "tokenizer",
        pos: Optional[Set[POS]] = None,
        stopwords: Optional[Set[str]] = None,
    ) -> List[str]:
        """
        异步提取关键词（支持所有模式）
        
        Args:
            text: 输入文本
            top_k: 返回前K个，None 表示全部
            mode: 模式 (tokenizer | llm | merge)
            pos: 词性过滤（临时覆盖）
            stopwords: 停用词（临时覆盖）
        
        Returns:
            关键词列表，无匹配返回 []
        """
        effective_pos = pos if pos is not None else self.default_pos
        effective_stopwords = stopwords if stopwords is not None else self.default_stopwords
        
        if mode == "tokenizer":
            logger.info("tokenizer 模式: 使用 tokenizer 结果")
            return self._extract_by_tokenizer(text, top_k, effective_pos, effective_stopwords)
        
        elif mode == "llm":
            logger.info("llm 模式: 使用 llm 结果")
            return await self._extract_by_llm(text, top_k, effective_pos, effective_stopwords)
        
        elif mode == "merge":
            logger.info("merge 模式: 使用 tokenizer 和 llm 结果")
            tk_kw = self._extract_by_tokenizer(text, top_k, effective_pos, effective_stopwords)
            llm_kw = await self._extract_by_llm(text, top_k, effective_pos, effective_stopwords)
            
            if not llm_kw and tk_kw:
                logger.info("merge 模式: LLM 无结果，使用 tokenizer 结果")
            
            merged = self._dedupe(llm_kw + tk_kw)  # LLM 优先
            return merged[:top_k] if top_k else merged
        
        else:
            logger.warning(f"未知模式: {mode}，使用 tokenizer")
            return self._extract_by_tokenizer(text, top_k, effective_pos, effective_stopwords)
    
    # ==================== 分词器提取 ====================
    
    def _extract_by_tokenizer(
        self,
        text: str,
        top_k: Optional[int],
        pos: Set[POS],
        stopwords: Set[str],
    ) -> List[str]:
        """分词器提取"""
        if not text or not text.strip():
            return []
        
        has_cn, has_en = self._detect_languages(text)
        
        if not has_cn and not has_en:
            return []
        
        keywords = []
        if has_cn:
            keywords.extend(self._extract_chinese(text, top_k, pos, stopwords))
        if has_en:
            keywords.extend(self._extract_english(text, top_k, pos, stopwords))
        
        result = self._dedupe(keywords)
        return result[:top_k] if top_k else result
    
    def _extract_chinese(
        self,
        text: str,
        top_k: Optional[int],
        pos: Set[POS],
        stopwords: Set[str],
    ) -> List[str]:
        """中文关键词（jieba TF-IDF）"""
        try:
            import jieba.analyse
            
            self._ensure_jieba_initialized()
            
            # 转换词性到 jieba 格式
            jieba_pos = self._convert_pos_to_jieba(pos)
            
            # jieba topK 不能为 None，动态计算
            jieba_top_k = self._calc_jieba_top_k(text, top_k)
            
            keywords = jieba.analyse.extract_tags(
                text,
                topK=jieba_top_k,
                withWeight=False,
                allowPOS=jieba_pos if jieba_pos else None,
            )
            
            filtered = [
                kw for kw in keywords
                if len(kw) >= self.min_len and kw not in stopwords
            ]
            
            return filtered[:top_k] if top_k else filtered
        
        except ImportError:
            logger.warning("jieba 未安装，跳过中文关键词提取")
            return []
    
    def _extract_english(
        self,
        text: str,
        top_k: Optional[int],
        pos: Set[POS],
        stopwords: Set[str],
    ) -> List[str]:
        """英文关键词（spaCy NER + 词性）"""
        try:
            tokenizer = MixedTokenizer.get_instance()
            nlp = tokenizer.get_spacy_nlp()
            
            if nlp is None:
                return self._extract_english_simple(text, top_k, stopwords)
            
            # 转换词性
            spacy_pos = self._convert_pos_to_spacy(pos)
            spacy_entities = self._convert_pos_to_spacy_entities(pos)
            
            # 只处理英文部分
            en_text = re.sub(r'[\u4e00-\u9fa5]+', ' ', text)
            doc = nlp(en_text)
            
            keywords = []
            
            # 1. 提取命名实体
            if spacy_entities:
                for ent in doc.ents:
                    if ent.label_ in spacy_entities:
                        if ent.text.lower() not in stopwords:
                            keywords.append(ent.text)
            
            # 2. 按词性提取
            for token in doc:
                if token.pos_ in spacy_pos:
                    w = token.text.strip()
                    if len(w) >= self.min_len and w.lower() not in stopwords and w not in keywords:
                        keywords.append(w)
            
            return keywords[:top_k] if top_k else keywords
        
        except Exception as e:
            logger.warning(f"spaCy 提取失败: {e}")
            return self._extract_english_simple(text, top_k, stopwords)
    
    def _extract_english_simple(
        self,
        text: str,
        top_k: Optional[int],
        stopwords: Set[str],
    ) -> List[str]:
        """简单英文提取（降级方案，无词性过滤）"""
        words = re.findall(r'\b[a-zA-Z][a-zA-Z0-9]*\b', text)
        filtered = [w for w in words if len(w) >= self.min_len and w.lower() not in stopwords]
        result = self._dedupe(filtered)
        return result[:top_k] if top_k else result
    
    # ==================== LLM 提取 ====================
    
    async def _extract_by_llm(
        self,
        text: str,
        top_k: Optional[int],
        pos: Set[POS],
        stopwords: Set[str],
    ) -> List[str]:
        """LLM 提取"""
        if not text or not text.strip():
            return []
        
        try:
            from dataflow.core.ai.factory import create_llm_client
            from dataflow.core.ai.base import LLMMessage, LLMRole
            
            client = await create_llm_client(scenario='general')
            
            # 动态构建词性描述
            pos_desc = "、".join([_LLM_POS_DESC.get(p, str(p)) for p in pos])
            
            # 动态构建数量要求
            count_desc = f"提取最多 {top_k} 个" if top_k else "提取所有"
            
            prompt = f"""从以下文本中{count_desc}关键词, 用来提供给搜索引擎，要从原文进行有效提取，比如话题、人物、物品、事件等, 不要提取无意义的关键词, 比如广告、无意义字符、乱码、群聊广告等。

                **词性要求**：只提取以下类型的词：{pos_desc}

                **输出要求**：
                - 不要重复
                - 按重要性排序
                - 不要解释

                **文本**：
                {text}
            """
                            
            schema = {
                "type": "object",
                "properties": {
                    "keywords": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "关键词列表"
                    }
                },
                "required": ["keywords"]
            }
            
            result = await client.chat_with_schema(
                [LLMMessage(role=LLMRole.USER, content=prompt)],
                response_schema=schema,
                temperature=0.3,
            )
            
            keywords = result.get("keywords", [])
            filtered = [
                kw.strip() for kw in keywords
                if kw and kw.strip() and kw.strip().lower() not in stopwords
            ]
            
            return filtered[:top_k] if top_k else filtered
        
        except Exception as e:
            logger.error(f"LLM 关键词提取失败: {e}")
            return []
    
    # ==================== 词性转换 ====================
    
    def _convert_pos_to_jieba(self, pos: Set[POS]) -> Tuple[str, ...]:
        """转换为 jieba 词性格式"""
        result = []
        for p in pos:
            if p in _JIEBA_POS_MAP:
                result.extend(_JIEBA_POS_MAP[p])
        return tuple(set(result)) if result else ()
    
    def _convert_pos_to_spacy(self, pos: Set[POS]) -> Set[str]:
        """转换为 spaCy 词性格式"""
        result = set()
        for p in pos:
            if p in _SPACY_POS_MAP:
                result.update(_SPACY_POS_MAP[p])
        return result
    
    def _convert_pos_to_spacy_entities(self, pos: Set[POS]) -> Set[str]:
        """转换为 spaCy NER 实体类型"""
        result = set()
        for p in pos:
            if p in _SPACY_ENTITY_MAP:
                result.update(_SPACY_ENTITY_MAP[p])
        return result
    
    # ==================== 工具方法 ====================
    
    def _detect_languages(self, text: str) -> Tuple[bool, bool]:
        """一次扫描检测中英文"""
        has_cn = has_en = False
        for char in text:
            if '\u4e00' <= char <= '\u9fa5':
                has_cn = True
            elif 'a' <= char.lower() <= 'z':
                has_en = True
            if has_cn and has_en:
                break
        return has_cn, has_en
    
    def _ensure_jieba_initialized(self):
        """线程安全的 jieba 初始化"""
        if self._jieba_initialized:
            return
        with self._jieba_lock:
            if self._jieba_initialized:
                return
            import jieba
            jieba.setLogLevel(jieba.logging.INFO)
            self._jieba_initialized = True
    
    def _calc_jieba_top_k(self, text: str, top_k: Optional[int]) -> int:
        """计算 jieba 的 topK 参数"""
        if top_k:
            return top_k * 3  # 多提取一些，后续过滤
        # 基于文本长度估算：每100字约10个关键词
        return max(50, len(text) // 10)
    
    def _dedupe(self, keywords: List[str]) -> List[str]:
        """去重（保持顺序）"""
        seen = set()
        result = []
        for kw in keywords:
            key = kw.lower().strip()
            if key and key not in seen:
                seen.add(key)
                result.append(kw)
        return result


# ==================== 便捷函数 ====================


def get_mixed_tokenizer() -> MixedTokenizer:
    """获取分词器单例"""
    return MixedTokenizer.get_instance()


def tokenize(text: str) -> List[str]:
    """
    快捷分词函数

    Args:
        text: 待分词的文本

    Returns:
        List[str]: 分词结果列表

    示例：
        >>> from dataflow.core.ai.tokensize import tokenize
        >>> tokens = tokenize("我喜欢Python")
        ['我', '喜欢', 'Python']
    """
    return get_mixed_tokenizer().tokenize(text)


def get_keyword_extractor() -> KeywordExtractor:
    """获取关键词提取器单例"""
    return KeywordExtractor.get_instance()


def extract_keywords(
    text: str,
    top_k: Optional[int] = None,
    mode: str = "tokenizer",
) -> List[str]:
    """
    同步提取关键词（简洁接口）
    
    Args:
        text: 输入文本
        top_k: 返回数量，None 全部
        mode: 模式（同步只支持 tokenizer）
    
    Returns:
        关键词列表，无匹配返回 []
    
    Example:
        >>> extract_keywords("苹果公司发布新款iPhone")
        ['苹果公司', 'iPhone']
        
        >>> extract_keywords("文本", top_k=3)
    
    复杂需求请使用 KeywordExtractor 实例。
    """
    return get_keyword_extractor().extract(text, top_k, mode)


async def extract_keywords_async(
    text: str,
    top_k: Optional[int] = None,
    mode: str = "tokenizer",
) -> List[str]:
    """
    异步提取关键词（简洁接口）
    
    Args:
        text: 输入文本
        top_k: 返回数量，None 全部
        mode: 模式 (tokenizer | llm | merge)
    
    Returns:
        关键词列表，无匹配返回 []
    
    Example:
        >>> await extract_keywords_async("文本", mode="llm")
        >>> await extract_keywords_async("文本", mode="merge", top_k=10)
    
    复杂需求请使用 KeywordExtractor 实例。
    """
    return await get_keyword_extractor().extract_async(text, top_k, mode)
