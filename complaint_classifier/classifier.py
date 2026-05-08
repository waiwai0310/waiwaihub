"""
分类引擎模块
使用 Trie 树实现高效的文本分类
"""

import re
import os
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Tuple, Optional, Any


def _drop_spans_strictly_contained(
    spans: List[Tuple[int, int, str, str]],
) -> List[Tuple[int, int, str, str]]:
    """
    去掉被更长命中区间严格包含的短命中，避免短词套在长词里误触发
    （例如「懂参数」落在「不懂参数」内仍被 find 命中）。
    按区间长度从长到短保留；再按位置、长度排序返回。
    """
    if len(spans) <= 1:
        return spans
    ordered = sorted(spans, key=lambda x: (x[1] - x[0]), reverse=True)
    kept: List[Tuple[int, int, str, str]] = []
    for s in ordered:
        sa, ea = s[0], s[1]
        if any(
            ta <= sa and ea <= te and (te - ta) > (ea - sa)
            for ta, te, _, _ in kept
        ):
            continue
        kept.append(s)
    kept.sort(key=lambda x: (x[0], -(x[1] - x[0])))
    return kept


class TrieNode:
    """Trie 树节点"""
    
    __slots__ = ['children', 'value', 'is_end']
    
    def __init__(self) -> None:
        self.children: Dict[str, "TrieNode"] = {}
        self.value: Optional[str] = None
        self.is_end: bool = False


class KeywordTrie:
    """
    关键词 Trie 树
    用于高效的多关键词匹配，时间复杂度 O(文本长度)
    """
    
    def __init__(self, keywords_dict: Dict[str, str]) -> None:
        """
        初始化 Trie 树
        
        Args:
            keywords_dict: {keyword: 标签值}
        """
        self.root = TrieNode()
        self.keywords_dict = keywords_dict
        self._build(keywords_dict)
    
    def _build(self, keywords_dict: Dict[str, str]) -> None:
        """构建 Trie 树"""
        for keyword, value in keywords_dict.items():
            self._insert(keyword.lower(), value)
    
    def _insert(self, keyword: str, value: str) -> None:
        """向 Trie 树中插入关键词"""
        node = self.root
        for char in keyword:
            if char not in node.children:
                node.children[char] = TrieNode()
            node = node.children[char]
        node.is_end = True
        node.value = value
    
    def search(self, text: str) -> Optional[str]:
        """
        在文本中搜索关键词，返回最长匹配的结果
        
        Args:
            text: 要搜索的文本
        
        Returns:
            标签值 或 None
        """
        text = text.lower()
        best_match = None
        best_length = 0
        
        # 遍历文本的每个位置，尝试匹配最长的关键词
        for i in range(len(text)):
            node = self.root
            j = i
            
            # 从位置 i 开始，贪心地匹配最长的关键词
            while j < len(text) and text[j] in node.children:
                node = node.children[text[j]]
                j += 1
                
                # 如果找到一个完整的关键词，记录它
                if node.is_end and (j - i) > best_length:
                    best_match = node.value
                    best_length = j - i
        
        return best_match

    def collect_all_matches(self, text: str) -> List[str]:
        """
        收集文本中命中的全部关键词对应标签（按首次出现位置排序，标签去重保序）。
        用于多选表头；同一标签只保留一次。
        """
        if not self.keywords_dict:
            return []
        text_l = text.lower()
        spans: List[Tuple[int, int, str]] = []
        for kw, val in self.keywords_dict.items():
            k = kw.lower()
            if not k:
                continue
            start = 0
            while True:
                i = text_l.find(k, start)
                if i < 0:
                    break
                spans.append((i, i + len(k), val))
                start = i + 1
        spans4 = [(a, b, "", v) for a, b, v in spans]
        spans4 = _drop_spans_strictly_contained(spans4)
        spans = [(a, b, v) for a, b, _, v in spans4]
        spans.sort(key=lambda x: (x[0], x[1]))
        out: List[str] = []
        seen: set[str] = set()
        for _, _, val in spans:
            if val not in seen:
                seen.add(val)
                out.append(val)
        return out

    def collect_match_items(self, text: str) -> List[Tuple[int, int, str, str]]:
        """
        收集文本中所有关键词命中项。
        返回: [(start, end, keyword, value), ...]，按位置排序。
        """
        if not self.keywords_dict:
            return []
        text_l = text.lower()
        out: List[Tuple[int, int, str, str]] = []
        for kw, val in self.keywords_dict.items():
            k = kw.lower()
            if not k:
                continue
            start = 0
            while True:
                i = text_l.find(k, start)
                if i < 0:
                    break
                out.append((i, i + len(k), kw, val))
                start = i + 1
        out = _drop_spans_strictly_contained(out)
        out.sort(key=lambda x: (x[0], -(x[1] - x[0])))
        return out


# 支持多标签合并输出（用 / 连接）的表头
MULTI_VALUE_HEADERS: frozenset = frozenset({"外观标签", "用户体验标签", "功能标签"})
MULTI_VALUE_JOIN = "/"

# 外观多选时，尺寸相关释义互斥（避免「尺寸小/尺寸大」同时出现）
APPEARANCE_SIZE_MUTEX: frozenset = frozenset({"尺寸小", "尺寸大", "尺寸合适", "尺寸错误"})


def _mutex_appearance_size(parts: List[str]) -> List[str]:
    """只保留规则命中顺序中第一个尺寸类标签，其余尺寸类标签丢弃。"""
    first: Optional[str] = None
    for p in parts:
        if p in APPEARANCE_SIZE_MUTEX:
            first = p
            break
    if first is None:
        return parts
    return [p for p in parts if p not in APPEARANCE_SIZE_MUTEX or p == first]


def _mutex_by_priority(
    parts: List[str],
    mutex_values: frozenset,
    priority: Tuple[str, ...],
) -> List[str]:
    """同一互斥组内只保留 priority 顺序中最先出现的那一个取值。"""
    present = [p for p in parts if p in mutex_values]
    if len(present) <= 1:
        return parts
    keep: Optional[str] = None
    for cand in priority:
        if cand in present:
            keep = cand
            break
    if keep is None:
        return parts
    return [p for p in parts if p not in mutex_values or p == keep]


def _mutex_appearance_all(parts: List[str]) -> List[str]:
    """外观多选：尺寸互斥 + 颜色褒贬互斥 + 外观褒贬互斥。"""
    parts = _mutex_appearance_size(parts)
    parts = _mutex_by_priority(
        parts,
        frozenset({"颜色好看", "颜色不好看"}),
        ("颜色不好看", "颜色好看"),
    )
    parts = _mutex_by_priority(
        parts,
        frozenset({"外观好看", "外观不好看"}),
        ("外观不好看", "外观好看"),
    )
    return parts


# 功能多选：薄厚垫表述互斥（抱怨薄优先于夸厚）
FUNC_THICK_MUTEX: frozenset = frozenset({"垫薄", "厚垫"})
FUNC_THICK_PRIORITY: Tuple[str, ...] = ("垫薄", "厚垫")


def _mutex_function_tags(parts: List[str]) -> List[str]:
    return _mutex_by_priority(parts, FUNC_THICK_MUTEX, FUNC_THICK_PRIORITY)


# 坐感三态互斥：同一条评论只保留一个（偏硬 > 一般 > 舒适，负面/体感问题优先）
UX_SEATING_MUTEX: frozenset = frozenset({"坐感舒适", "坐感一般", "坐感偏硬"})
UX_SEATING_PRIORITY: Tuple[str, ...] = ("坐感偏硬", "坐感一般", "坐感舒适")


def _mutex_ux_seating(parts: List[str]) -> List[str]:
    present = [p for p in parts if p in UX_SEATING_MUTEX]
    if len(present) <= 1:
        return parts
    keep: Optional[str] = None
    for cand in UX_SEATING_PRIORITY:
        if cand in present:
            keep = cand
            break
    if keep is None:
        return parts
    return [p for p in parts if p not in UX_SEATING_MUTEX or p == keep]


UX_SUPPORT_MUTEX: frozenset = frozenset({"靠背支撑好", "支撑不够"})
UX_SUPPORT_PRIORITY: Tuple[str, ...] = ("支撑不够", "靠背支撑好")


def _mutex_ux_support(parts: List[str]) -> List[str]:
    return _mutex_by_priority(parts, UX_SUPPORT_MUTEX, UX_SUPPORT_PRIORITY)


NEGATION_TOKENS: Tuple[str, ...] = ("不", "没", "无", "非", "别")
NEGATION_PREFIXES: Tuple[str, ...] = ("不太", "不够", "不算", "不是", "并不", "并非", "没有", "没那么")
EN_NEGATION_PREFIX_RE = re.compile(r"(?:\bno\b|\bnot\b|\bdon't\b|\bdoesn't\b|\bdidn't\b|\bnever\b)\s*$", re.IGNORECASE)
NEGATION_SUFFIX_RE = re.compile(r"(不好|并不好|不太好|不是很好|不佳|不准|不行|不对|较差|很差|太差|偏差|失真)")
TURN_SPLIT_RE = re.compile(r"(但是|不过|但|然而|只是)")
SENTENCE_SPLIT_RE = re.compile(r"[。！？!\?\n]+")
CLAUSE_SPLIT_RE = re.compile(r"[，,；;]")
SHORT_KEYWORD_CONTEXT_RE = re.compile(r"(画面|播放|系统|界面|运行|游戏|投屏|对焦|卡顿|延迟|噪音|风扇)")
NEGATIVE_HINT_RE = re.compile(
    r"(差|不足|不清|不准|模糊|卡顿|故障|失真|偏色|发灰|发白|吵|噪音|刺眼|太亮|太暗|不值|慢|失败|断连|过热|烫|粗糙|廉价|太假|假得明显)"
)
POSITIVE_HINT_RE = re.compile(
    r"(好|满意|清晰|准确|自然|稳定|顺滑|流畅|静音|舒适|精准|丰富|便携|值|划算|耐用)"
)
DEGREE_STRONG_RE = re.compile(r"(非常|特别|极其|太|超|超级)")
DEGREE_MID_RE = re.compile(r"(很|比较)")
DEGREE_WEAK_RE = re.compile(r"(有点|稍微|略)")
ANALOGY_RE = re.compile(r"(像|好像|类似)")
COMPARE_POS_RE = re.compile(
    r"(比.{0,12}(好|更好|更清晰|更亮|更稳|更流畅)|better than|more stable than|clearer than|brighter than)"
)
COMPARE_NEG_RE = re.compile(
    r"(不如.{0,12}|没有.{0,12}(好|清晰|稳定|流畅)|比.{0,12}(差|更差|更糟)|worse than|not as .{0,12} as|inferior to)"
)
RESOLUTION_HINT_RE = re.compile(r"(退货|换货|换新|替换|补发|修复|修好|解决|replac|refund|fixed|resolved)")
FINAL_EVAL_POS_RE = re.compile(r"(现在|目前|后来|之后|最终|最后).{0,16}(满意|很好|不错|正常|推荐)|now.{0,16}(happy|satisfied|works)")
CURRENT_ITEM_POS_RE = re.compile(
    r"((this|the)\s+(one|tree|plant).{0,40}(great|good|recommend|love|worth|realistic|nice))|"
    r"(this\s+one.{0,20}(is|looks|feels).{0,20}(great|good|nice|realistic|worth))|"
    r"(这个(款|树|植物).{0,20}(很好|不错|推荐|喜欢|值得|逼真))",
    re.IGNORECASE,
)
PRICE_CONCESSION_RE = re.compile(r"(但|但是|不过|然而|只是|but|though).{0,20}(这个价位|这个价格|价位来说|for the price|at this price)")
EXPECTATION_POS_RE = re.compile(r"(本来以为|原以为|以为|没想到|超出预期|高于预期|better than expected|exceeded expectations)")
CLAIM_MISMATCH_RE = re.compile(r"(宣传|标称|写的是|宣称|advertis|claimed|listed as).{0,30}(实际|其实|only|却|but).{0,20}")
OTHER_PRODUCT_NEG_RE = re.compile(
    r"(?:\b(other|others|another)\b.{0,40}\b(bad quality|poor quality|cheap|fake|plastic|not good|low quality)\b)|"
    r"(?:其他.{0,30}(质量差|做工差|太假|廉价|塑料感强))",
    re.IGNORECASE,
)
HISTORY_COMPARE_NEG_RE = re.compile(
    r"(return(?:ed)?|退回|退货|换过|试过).{0,50}(bad quality|poor quality|cheap|质量差|质量不好|做工差|廉价)",
    re.IGNORECASE,
)
EASY_CARE_HINT_RE = re.compile(r"(易于护理的替代品|easy-care alternative|easy care alternative|low maintenance alternative)")
NEGATED_VALUE_MAP: Dict[str, str] = {
    "清晰": "模糊",
    "很清楚": "模糊",
    "文字清晰": "模糊",
    "色彩好": "色彩差",
    "色彩准确": "偏色",
    "亮度满意": "亮度不足",
    "亮度不错": "亮度不足",
    "流畅": "系统卡顿",
    "稳定": "断连",
    "静音": "噪音大",
    "音质好": "音质差",
    # 负向被否定时，回退到更合理的正向/中性标签
    "容易掉": "不掉叶",
    "掉叶严重": "不掉叶",
    "有异味": "没有异味",
    "假得明显": "非常逼真",
    "材质差": "材质好",
    "质量差": "质量好",
    "不稳": "很稳固",
    "容易倒": "很稳固",
}


class ClassifyEngine:
    """
    分类引擎（优化版本）
    
    使用 Trie 树替代线性搜索，性能提升 5-10 倍
    """
    
    def __init__(
        self,
        output_columns: List[str],
        exact_rules: Dict[str, Dict[str, str]],
        fuzzy_rules: Dict[str, List[Tuple[str, str]]],
        en_fallback_rules: Dict[str, Dict[str, str]],
        label_priority_by_header: Dict[str, Dict[str, int]],
        negative_patterns: List[str],
        neutral_patterns: Optional[List[str]] = None,
        height_rules: Optional[Dict[str, Any]] = None,
        debug_options: Optional[Dict[str, Any]] = None,
        rule_priority: Optional[List[str]] = None,
    ) -> None:
        """
        初始化分类引擎
        
        Args:
            output_columns: 需要输出的全部表头
            exact_rules: 精确匹配规则 {表头: {keyword: 标签值}}
            fuzzy_rules: 模糊匹配规则 {表头: [(regex_pattern, 标签值), ...]}
            negative_patterns: 识别差评的正则列表
        """
        self.output_columns = output_columns
        self.height_rules = height_rules or {}
        self.height_header = str(self.height_rules.get("header", "尺寸/高度")).strip() or "尺寸/高度"
        self.height_expected_cm = self._to_cm(self.height_rules.get("expected_height", self.height_rules.get("expected_cm")))
        self.height_tolerance_cm = float(self.height_rules.get("tolerance_cm", 8))
        self.height_label_small = str(self.height_rules.get("label_small", "比预期小"))
        self.height_label_large = str(self.height_rules.get("label_large", "比预期大"))
        self.height_label_ok = str(self.height_rules.get("label_ok", "尺寸合适"))
        self.height_mismatch_hint = re.compile(
            r"(比描述短|比广告短|不达标|不符合标注|不是.*英尺|没有.*英尺|更像\d+(\.\d+)?英尺|只有\d+(\.\d+)?英尺|矮很多|太矮)",
            re.IGNORECASE,
        )

        # 1) 精确匹配规则：每个表头一个 Trie
        self.exact_tries: Dict[str, KeywordTrie] = {}
        for header, mapping in exact_rules.items():
            normalized = {
                str(k).strip().lower(): str(v).strip()
                for k, v in mapping.items()
                if str(k).strip() and str(v).strip()
            }
            if normalized:
                self.exact_tries[header] = KeywordTrie(normalized)

        # 2) 模糊匹配规则：每个表头一个正则列表
        self.fuzzy_patterns_by_header: Dict[str, List[Tuple[re.Pattern, str]]] = {}
        for header, items in fuzzy_rules.items():
            compiled_items: List[Tuple[re.Pattern, str]] = []
            for pattern, value in items:
                try:
                    compiled_pattern = re.compile(pattern, re.IGNORECASE)
                    compiled_items.append((compiled_pattern, value))
                except re.error as e:
                    print(f"⚠️ 跳过无效正则: {pattern} -> {e}")
            if compiled_items:
                self.fuzzy_patterns_by_header[header] = compiled_items

        # 2.5) 英文关键词兜底规则（最低优先级）
        self.en_fallback_tries: Dict[str, KeywordTrie] = {}
        for header, mapping in en_fallback_rules.items():
            normalized = {
                str(k).strip().lower(): str(v).strip()
                for k, v in mapping.items()
                if str(k).strip() and str(v).strip()
            }
            if normalized:
                self.en_fallback_tries[header] = KeywordTrie(normalized)

        # 3) 差评识别正则
        self.negative_patterns: List[re.Pattern] = []
        for pattern in negative_patterns:
            try:
                self.negative_patterns.append(re.compile(pattern, re.IGNORECASE))
            except re.error as e:
                print(f"⚠️ 跳过无效差评正则: {pattern} -> {e}")

        # 4) 中性语气识别（用于“还行/一般/可接受”类语义微调）
        self.neutral_patterns: List[re.Pattern] = []
        for pattern in (neutral_patterns or []):
            try:
                self.neutral_patterns.append(re.compile(pattern, re.IGNORECASE))
            except re.error as e:
                print(f"⚠️ 跳过无效中性正则: {pattern} -> {e}")

        # 5) 调试命中日志
        dbg = debug_options or {}
        self.debug_enabled = bool(dbg.get("enabled", False))
        self.debug_log_file = str(dbg.get("log_file", "")).strip()
        self._debug_entries: List[str] = []
        self.rule_priority = rule_priority or ["exact_rules", "fuzzy_rules", "en_keyword_to_label_map"]
        self.label_priority_by_header = label_priority_by_header
        
        # 统计信息
        self.match_stats: Dict[str, int] = {
            'exact': 0,
            'fuzzy': 0,
            'default': 0
        }

    @staticmethod
    def _to_cm(value: Any) -> Optional[float]:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        s = str(value).strip().lower()
        m = re.search(r"(\d+(?:\.\d+)?)", s)
        if not m:
            return None
        num = float(m.group(1))
        if "cm" in s or "厘米" in s:
            return num
        if "m" in s and "cm" not in s:
            return num * 100
        if "ft" in s or "feet" in s or "foot" in s or "英尺" in s:
            return num * 30.48
        return num

    @staticmethod
    def _extract_heights_cm(text: str) -> List[float]:
        out: List[float] = []
        for m in re.finditer(r"(\d+(?:\.\d+)?)\s*(cm|厘米)", text, re.IGNORECASE):
            out.append(float(m.group(1)))
        for m in re.finditer(r"(\d+(?:\.\d+)?)\s*(ft|feet|foot|英尺)", text, re.IGNORECASE):
            out.append(float(m.group(1)) * 30.48)
        # 诸如“5英尺7”/“5'7”按英尺+英寸解析
        for m in re.finditer(r"(\d+)\s*(?:英尺|ft|')\s*(\d{1,2})", text, re.IGNORECASE):
            out.append(float(m.group(1)) * 30.48 + float(m.group(2)) * 2.54)
        return out

    def _height_label_from_text(self, text: str) -> Optional[str]:
        if not self.height_expected_cm:
            return None
        vals = self._extract_heights_cm(text)
        if not vals:
            # 没有数值时，至少允许“明显不达标”类语义触发
            return self.height_label_small if self.height_mismatch_hint.search(text) else None
        observed = max(vals)
        if observed < (self.height_expected_cm - self.height_tolerance_cm):
            return self.height_label_small
        if observed > (self.height_expected_cm + self.height_tolerance_cm):
            return self.height_label_large
        return self.height_label_ok

    def _debug_log(self, line: str) -> None:
        if self.debug_enabled:
            self._debug_entries.append(line)

    @staticmethod
    def _is_negated(text: str, start: int, end: int, keyword: str) -> bool:
        """关键词前后出现否定线索时，认为该命中被否定（否定优先）。"""
        if start <= 0:
            left_neg = False
        else:
            left = text[max(0, start - 4):start]
            if any(left.endswith(p) for p in NEGATION_PREFIXES):
                return True
            left_neg = any(left.endswith(t) for t in NEGATION_TOKENS) and keyword and not keyword.startswith(("不", "没", "无"))
            if left_neg:
                return True
            # 英文否定前缀（not / don't / doesn't ...）
            left_en = text[max(0, start - 14):start]
            if EN_NEGATION_PREFIX_RE.search(left_en):
                return True

        # 后缀否定：如“色彩准确度不好”“清晰但不够清晰”
        right = text[end:min(len(text), end + 10)]
        if NEGATION_SUFFIX_RE.search(right):
            return True
        return False

    @staticmethod
    def _allow_short_keyword(text: str, start: int, end: int, keyword: str) -> bool:
        """短词边界与上下文控制，减少“卡扣/卡槽”类误伤。"""
        if len(keyword) > 1:
            return True
        # 单字短词，要求附近出现与体验相关上下文，否则跳过
        ctx = text[max(0, start - 3):min(len(text), end + 3)]
        if SHORT_KEYWORD_CONTEXT_RE.search(ctx):
            return True
        # 特例：若短词自身语义非常明确，允许
        if keyword in {"值"}:
            return True
        return False

    @staticmethod
    def _sentiment_of_value(value: str, force_negative: bool = False) -> int:
        """
        粗粒度极性：负面=-1，正面=1，未知=0。
        force_negative 用于“正向词被否定”场景。
        """
        if force_negative:
            return -1
        if NEGATIVE_HINT_RE.search(value):
            return -1
        if POSITIVE_HINT_RE.search(value):
            return 1
        return 0

    @staticmethod
    def _split_with_turning(text: str) -> List[Tuple[str, int]]:
        """
        按“但是/不过/但/然而”切段，转折后的片段权重更高。
        返回 [(segment, weight)]。
        """
        raw_sentences = [s.strip() for s in SENTENCE_SPLIT_RE.split(text) if s.strip()]
        if not raw_sentences:
            raw_sentences = [text]
        out: List[Tuple[str, int]] = []
        for sentence in raw_sentences:
            parts = TURN_SPLIT_RE.split(sentence)
            current_weight = 1
            for part in parts:
                p = part.strip()
                if not p:
                    continue
                if TURN_SPLIT_RE.fullmatch(p):
                    current_weight = 2
                    continue
                out.append((p, current_weight))
        return out or [(text, 1)]

    @staticmethod
    def _degree_bonus(seg: str, start: int) -> int:
        """程度词强度加权：强>中>弱。"""
        left = seg[max(0, start - 6):start]
        if DEGREE_STRONG_RE.search(left):
            return 4
        if DEGREE_MID_RE.search(left):
            return 2
        if DEGREE_WEAK_RE.search(left):
            return 1
        return 0

    @staticmethod
    def _comparison_bonus(seg: str, polarity: int) -> int:
        """
        对比结构加权：
        - 正向候选命中“比XX好”加分
        - 负向候选命中“不如XX/比XX差”加分
        """
        if polarity > 0 and COMPARE_POS_RE.search(seg):
            return 3
        if polarity < 0 and COMPARE_NEG_RE.search(seg):
            return 3
        return 0

    @staticmethod
    def _analogy_bonus(seg: str, polarity: int) -> int:
        """
        类比词加权（像/好像/类似）：
        通常用于“像吹风机/像雾一样”等强描述，负向更高权重。
        """
        if not ANALOGY_RE.search(seg):
            return 0
        return 2 if polarity < 0 else 1

    @staticmethod
    def _price_bonus(seg: str, polarity: int) -> int:
        """“但/不过 + 以这个价位”让步结构：低预期满足时给正向候选加权。"""
        if polarity > 0 and PRICE_CONCESSION_RE.search(seg):
            return 4
        return 0

    @staticmethod
    def _expectation_bonus(seg: str, polarity: int) -> int:
        """“没想到/超预期”结构作为强正向信号。"""
        if polarity > 0 and EXPECTATION_POS_RE.search(seg):
            return 4
        return 0

    @staticmethod
    def _claim_mismatch_bonus(seg: str, polarity: int) -> int:
        """“宣传 vs 实际不符”结构：负向候选额外加权。"""
        if polarity < 0 and CLAIM_MISMATCH_RE.search(seg):
            return 5
        return 0

    @staticmethod
    def _prefer_final_positive(text: str) -> bool:
        """出现“问题已处理/替换后，现在满意”等语义时，优先最终正向结论。"""
        return bool(RESOLUTION_HINT_RE.search(text) and FINAL_EVAL_POS_RE.search(text))

    @staticmethod
    def _prefer_current_item_positive(text: str) -> bool:
        """出现“this one/这个款很不错”等当前商品明确正向结论时，优先正向。"""
        return bool(CURRENT_ITEM_POS_RE.search(text))

    @staticmethod
    def _is_other_product_negative_context(seg: str, polarity: int) -> bool:
        """
        负向词命中在“其他产品/别人家的产品”语境时，不应归因到当前商品。
        例如：after returning many others that were bad quality.
        """
        return polarity < 0 and bool(OTHER_PRODUCT_NEG_RE.search(seg) or HISTORY_COMPARE_NEG_RE.search(seg))

    def _collect_header_candidates(self, text: str, header: str) -> List[Tuple[int, int, int, str]]:
        """
        收集单个表头的候选命中：
        (priority_score, polarity, pos, value)
        """
        candidates: List[Tuple[int, int, int, str]] = []
        segments = self._split_with_turning(text)
        base_pos_offset = 0
        for seg, seg_weight in segments:
            trie = self.exact_tries.get(header)
            if trie:
                for start, end, kw, val in trie.collect_match_items(seg):
                    if not self._allow_short_keyword(seg, start, end, kw):
                        continue
                    negated = self._is_negated(seg, start, end, kw)
                    out_val = NEGATED_VALUE_MAP.get(str(val), str(val)) if negated else str(val)
                    polarity = self._sentiment_of_value(out_val, force_negative=(negated and out_val == str(val)))
                    # 对比负向结构优先：如“ 不如上一台清晰 ”应反转为负向语义
                    if COMPARE_NEG_RE.search(seg) and polarity > 0:
                        out_val = NEGATED_VALUE_MAP.get(out_val, out_val)
                        polarity = self._sentiment_of_value(out_val, force_negative=True)
                    if self._is_other_product_negative_context(seg, polarity):
                        continue
                    length_bonus = min(len(kw), 8)
                    degree_bonus = self._degree_bonus(seg, start)
                    cmp_bonus = self._comparison_bonus(seg, polarity)
                    analogy_bonus = self._analogy_bonus(seg, polarity)
                    price_bonus = self._price_bonus(seg, polarity)
                    exp_bonus = self._expectation_bonus(seg, polarity)
                    mismatch_bonus = self._claim_mismatch_bonus(seg, polarity)
                    neutral_bonus = 2 if (polarity == 0 and any(p.search(seg) for p in self.neutral_patterns)) else 0
                    score = (
                        (30 + seg_weight * 10 + length_bonus + degree_bonus + cmp_bonus + analogy_bonus + price_bonus + exp_bonus + mismatch_bonus + neutral_bonus)
                        if negated
                        else (20 + seg_weight * 10 + length_bonus + degree_bonus + cmp_bonus + analogy_bonus + price_bonus + exp_bonus + mismatch_bonus + neutral_bonus)
                    )
                    candidates.append((score, polarity, base_pos_offset + start, out_val))
                    self._debug_log(f"[EXACT] {header} | kw={kw} | val={out_val} | score={score} | seg={seg[:80]}")
                    self.match_stats['exact'] += 1

            fuzzy_items = self.fuzzy_patterns_by_header.get(header, [])
            for pattern, value in fuzzy_items:
                m = pattern.search(seg)
                if not m:
                    continue
                start = m.start()
                matched_kw = m.group(0) or ""
                if matched_kw and not self._allow_short_keyword(seg, start, m.end(), matched_kw):
                    continue
                negated = self._is_negated(seg, start, m.end(), matched_kw)
                out_val = NEGATED_VALUE_MAP.get(str(value), str(value)) if negated else str(value)
                polarity = self._sentiment_of_value(out_val, force_negative=(negated and out_val == str(value)))
                if COMPARE_NEG_RE.search(seg) and polarity > 0:
                    out_val = NEGATED_VALUE_MAP.get(out_val, out_val)
                    polarity = self._sentiment_of_value(out_val, force_negative=True)
                if self._is_other_product_negative_context(seg, polarity):
                    continue
                degree_bonus = self._degree_bonus(seg, start)
                cmp_bonus = self._comparison_bonus(seg, polarity)
                analogy_bonus = self._analogy_bonus(seg, polarity)
                price_bonus = self._price_bonus(seg, polarity)
                exp_bonus = self._expectation_bonus(seg, polarity)
                mismatch_bonus = self._claim_mismatch_bonus(seg, polarity)
                neutral_bonus = 2 if (polarity == 0 and any(p.search(seg) for p in self.neutral_patterns)) else 0
                score = (
                    10 + seg_weight * 10 + (5 if negated else 0)
                    + degree_bonus + cmp_bonus + analogy_bonus + price_bonus + exp_bonus + mismatch_bonus + neutral_bonus
                )
                candidates.append((score, polarity, base_pos_offset + start, out_val))
                self._debug_log(f"[FUZZY] {header} | pattern={pattern.pattern} | val={out_val} | score={score} | seg={seg[:80]}")
                self.match_stats['fuzzy'] += 1
            base_pos_offset += len(seg) + 1
        return candidates

    def _pick_best_candidate(
        self,
        text: str,
        header: str,
        candidates: List[Tuple[int, int, int, str]],
    ) -> Optional[str]:
        if not candidates:
            return None
        # 业务优先：明确“易于护理替代品”时，核心痛点优先落到「不想维护」
        if header == "核心痛点" and EASY_CARE_HINT_RE.search(text):
            for _, _, _, val in sorted(candidates, key=lambda x: (-x[0], x[2])):
                if str(val) == "不想维护":
                    return "不想维护"
        pri = self._get_label_priority_map(header)
        if pri:
            candidates = sorted(candidates, key=lambda x: (pri.get(str(x[3]), 10**6), -x[0], x[2]))
            return candidates[0][3]
        if self._prefer_final_positive(text) or self._prefer_current_item_positive(text):
            positives = [c for c in candidates if c[1] > 0]
            pool = positives if positives else candidates
        else:
            negatives = [c for c in candidates if c[1] < 0]
            pool = negatives if negatives else candidates
        pool.sort(key=lambda x: (-x[0], x[2]))
        return pool[0][3] if pool else None

    def _get_label_priority_map(self, header: str) -> Dict[str, int]:
        return self.label_priority_by_header.get(header, {})

    def _match_header_exact_only(self, text: str, header: str) -> Optional[str]:
        trie = self.exact_tries.get(header)
        if not trie:
            return None
        candidates: List[Tuple[int, int, int, str]] = []
        segments = self._split_with_turning(text)
        base_pos_offset = 0
        for seg, seg_weight in segments:
            for start, end, kw, val in trie.collect_match_items(seg):
                if not self._allow_short_keyword(seg, start, end, kw):
                    continue
                negated = self._is_negated(seg, start, end, kw)
                out_val = NEGATED_VALUE_MAP.get(str(val), str(val)) if negated else str(val)
                polarity = self._sentiment_of_value(out_val, force_negative=(negated and out_val == str(val)))
                if COMPARE_NEG_RE.search(seg) and polarity > 0:
                    out_val = NEGATED_VALUE_MAP.get(out_val, out_val)
                    polarity = self._sentiment_of_value(out_val, force_negative=True)
                if self._is_other_product_negative_context(seg, polarity):
                    continue
                length_bonus = min(len(kw), 8)
                degree_bonus = self._degree_bonus(seg, start)
                cmp_bonus = self._comparison_bonus(seg, polarity)
                analogy_bonus = self._analogy_bonus(seg, polarity)
                price_bonus = self._price_bonus(seg, polarity)
                exp_bonus = self._expectation_bonus(seg, polarity)
                mismatch_bonus = self._claim_mismatch_bonus(seg, polarity)
                neutral_bonus = 2 if (polarity == 0 and any(p.search(seg) for p in self.neutral_patterns)) else 0
                score = (
                    (30 + seg_weight * 10 + length_bonus + degree_bonus + cmp_bonus + analogy_bonus + price_bonus + exp_bonus + mismatch_bonus + neutral_bonus)
                    if negated
                    else (20 + seg_weight * 10 + length_bonus + degree_bonus + cmp_bonus + analogy_bonus + price_bonus + exp_bonus + mismatch_bonus + neutral_bonus)
                )
                candidates.append((score, polarity, base_pos_offset + start, out_val))
                self._debug_log(f"[EXACT] {header} | kw={kw} | val={out_val} | score={score} | seg={seg[:80]}")
                self.match_stats["exact"] += 1
            base_pos_offset += len(seg) + 1
        return self._pick_best_candidate(text, header, candidates)

    def _match_header_fuzzy_only(self, text: str, header: str) -> Optional[str]:
        fuzzy_items = self.fuzzy_patterns_by_header.get(header, [])
        if not fuzzy_items:
            return None
        candidates: List[Tuple[int, int, int, str]] = []
        segments = self._split_with_turning(text)
        base_pos_offset = 0
        for seg, seg_weight in segments:
            for pattern, value in fuzzy_items:
                m = pattern.search(seg)
                if not m:
                    continue
                start = m.start()
                matched_kw = m.group(0) or ""
                if matched_kw and not self._allow_short_keyword(seg, start, m.end(), matched_kw):
                    continue
                negated = self._is_negated(seg, start, m.end(), matched_kw)
                out_val = NEGATED_VALUE_MAP.get(str(value), str(value)) if negated else str(value)
                polarity = self._sentiment_of_value(out_val, force_negative=(negated and out_val == str(value)))
                if COMPARE_NEG_RE.search(seg) and polarity > 0:
                    out_val = NEGATED_VALUE_MAP.get(out_val, out_val)
                    polarity = self._sentiment_of_value(out_val, force_negative=True)
                if self._is_other_product_negative_context(seg, polarity):
                    continue
                degree_bonus = self._degree_bonus(seg, start)
                cmp_bonus = self._comparison_bonus(seg, polarity)
                analogy_bonus = self._analogy_bonus(seg, polarity)
                price_bonus = self._price_bonus(seg, polarity)
                exp_bonus = self._expectation_bonus(seg, polarity)
                mismatch_bonus = self._claim_mismatch_bonus(seg, polarity)
                neutral_bonus = 2 if (polarity == 0 and any(p.search(seg) for p in self.neutral_patterns)) else 0
                score = 10 + seg_weight * 10 + (5 if negated else 0) + degree_bonus + cmp_bonus + analogy_bonus + price_bonus + exp_bonus + mismatch_bonus + neutral_bonus
                candidates.append((score, polarity, base_pos_offset + start, out_val))
                self._debug_log(f"[FUZZY] {header} | pattern={pattern.pattern} | val={out_val} | score={score} | seg={seg[:80]}")
                self.match_stats["fuzzy"] += 1
            base_pos_offset += len(seg) + 1
        return self._pick_best_candidate(text, header, candidates)

    def _match_header_en_fallback(self, text: str, header: str) -> Optional[str]:
        trie = self.en_fallback_tries.get(header)
        if not trie:
            return None
        val = trie.search(text)
        if val:
            self._debug_log(f"[EN_FALLBACK] {header} | val={val}")
        return val

    def _match_header_multi(self, text: str, header: str) -> str:
        """多选表头：exact 与 fuzzy 全部命中，标签去重后按顺序用 / 连接"""
        parts: List[str] = []
        seen: set[str] = set()

        trie = self.exact_tries.get(header)
        if trie:
            for val in trie.collect_all_matches(text):
                if val not in seen:
                    seen.add(val)
                    parts.append(val)
                    self.match_stats['exact'] += 1

        fuzzy_items = self.fuzzy_patterns_by_header.get(header, [])
        for pattern, value in fuzzy_items:
            if pattern.search(text):
                v = str(value).strip()
                if v and v not in seen:
                    seen.add(v)
                    parts.append(v)
                    self.match_stats['fuzzy'] += 1

        if header == "外观标签":
            parts = _mutex_appearance_all(parts)
        if header == "用户体验标签":
            parts = _mutex_ux_seating(parts)
            parts = _mutex_ux_support(parts)
        if header == "功能标签":
            parts = _mutex_function_tags(parts)

        return MULTI_VALUE_JOIN.join(parts) if parts else ""

    def _match_header(self, text: str, header: str) -> Optional[str]:
        """对单个表头按优先级链匹配（exact -> fuzzy -> en_fallback）。"""
        if header in MULTI_VALUE_HEADERS:
            s = self._match_header_multi(text, header)
            return s if s else None
        for stage in self.rule_priority:
            if stage == "exact_rules":
                matched = self._match_header_exact_only(text, header)
            elif stage == "fuzzy_rules":
                matched = self._match_header_fuzzy_only(text, header)
            elif stage == "en_keyword_to_label_map":
                matched = self._match_header_en_fallback(text, header)
            else:
                matched = None
            if matched:
                return matched
        return None

    def classify(self, text: str) -> Dict[str, str]:
        """
        对单条文本进行分类
        
        Args:
            text: 已清洗的文本
        
        Returns:
            {表头: 标签值}
        """
        result: Dict[str, str] = {col: "" for col in self.output_columns}
        if "是否差评" in result:
            result["是否差评"] = "否"

        # 处理空值或纯标点符号
        if not text or re.fullmatch(r"[。，,\s]*", text):
            self.match_stats['default'] += 1
            return result

        has_any_tag = False
        for header in self.output_columns:
            if header == "是否差评":
                continue
            matched_value = self._match_header(text, header)
            if matched_value:
                result[header] = matched_value
                has_any_tag = True

        # 数值化高度补充规则：当尺寸/高度未命中时，用抽取到的数值进行兜底判断
        if self.height_header in result and not result.get(self.height_header):
            h_label = self._height_label_from_text(text)
            if h_label:
                result[self.height_header] = h_label
                has_any_tag = True
                self._debug_log(f"[HEIGHT] {self.height_header} | val={h_label} | text={text[:120]}")

        # 差评判断：命中负向情绪或任一标签命中
        if "是否差评" in result:
            if has_any_tag or any(p.search(text) for p in self.negative_patterns):
                result["是否差评"] = "是"

        if not has_any_tag:
            self.match_stats['default'] += 1
        if self.debug_enabled and self.debug_log_file and self._debug_entries:
            try:
                folder = os.path.dirname(self.debug_log_file)
                if folder:
                    os.makedirs(folder, exist_ok=True)
                with open(self.debug_log_file, "a", encoding="utf-8") as f:
                    f.write("\n".join(self._debug_entries) + "\n")
            except Exception:
                pass
            finally:
                self._debug_entries = []
        return result

    def classify_batch(self, texts: List[str]) -> List[Dict[str, str]]:
        """
        批量分类
        
        Args:
            texts: 文本列表
        
        Returns:
            分类结果列表
        """
        return [self.classify(text) for text in texts]

    def classify_batch_parallel(
        self,
        texts: List[str],
        num_workers: int = 4
    ) -> List[Dict[str, str]]:
        """
        并行批量分类（可选使用）
        
        Args:
            texts: 文本列表
            num_workers: 线程数量
        
        Returns:
            分类结果列表（顺序与输入一致）
        """
        if not texts:
            return []

        results: List[Optional[Dict[str, str]]] = [None] * len(texts)

        with ThreadPoolExecutor(max_workers=num_workers) as executor:
            future_to_index = {
                executor.submit(self.classify, text): idx
                for idx, text in enumerate(texts)
            }

            for future in as_completed(future_to_index):
                idx = future_to_index[future]
                try:
                    results[idx] = future.result()
                except Exception:
                    # 出错时退回默认分类，避免中断整体任务
                    results[idx] = self.classify("")

        # 类型收窄：此时 results 中已经不会有 None
        return [r for r in results if r is not None]
    
    def get_stats(self) -> Dict[str, int]:
        """获取匹配统计"""
        return self.match_stats.copy()
    
    @classmethod
    def build_from_config(
        cls,
        config: Dict,
        df_category
    ) -> 'ClassifyEngine':
        """
        从配置和 DataFrame 构建分类器
        
        Args:
            config: 配置字典
            df_category: 包含分类规则的 DataFrame
        
        Returns:
            ClassifyEngine 实例
        """
        rules_config = config['rules']
        col_settings = config['column_settings']

        output_columns = list(col_settings.get('common_output_columns', [])) + list(
            col_settings.get('custom_output_columns', [])
        )

        header_alias_map = rules_config.get("header_alias_map", {})

        def resolve_header(raw_header: str) -> str:
            h = str(raw_header).strip()
            if not h:
                return h
            if h in output_columns:
                return h
            aliased = str(header_alias_map.get(h, "")).strip()
            if aliased and aliased in output_columns:
                return aliased
            # 通用兜底：将“XX标签”映射到包含“XX”的输出列（如 尺寸标签 -> 尺寸/高度）
            stem = h[:-2] if h.endswith("标签") else h
            for oc in output_columns:
                if stem and stem in oc:
                    return oc
            return h

        exact_rules: Dict[str, Dict[str, str]] = {}
        label_priority_by_header: Dict[str, Dict[str, int]] = {}
        cluster_keywords_by_header: Dict[str, set[str]] = {}
        cluster_labels_by_header: Dict[str, set[str]] = {}

        # exact 语义簇（可选）：支持 {header: {HIGH:[...], MID:[...], LOW:[...]}}
        # 代表值默认取每个簇第一个词；并记录标签优先级用于冲突消解。
        level_order = list(rules_config.get("label_priority_order", ["HIGH", "MID", "LOW"]))
        for header, level_map in rules_config.get("exact_semantic_clusters", {}).items():
            resolved = resolve_header(header)
            if not isinstance(level_map, dict):
                continue
            for rank, level in enumerate(level_order):
                kws = level_map.get(level, [])
                if not isinstance(kws, list) or not kws:
                    continue
                rep = str(kws[0]).strip()
                if not rep:
                    continue
                label_priority_by_header.setdefault(resolved, {})[rep] = rank
                cluster_labels_by_header.setdefault(resolved, set()).add(rep)
                for kw in kws:
                    kw_s = str(kw).strip()
                    if kw_s:
                        cluster_keywords_by_header.setdefault(resolved, set()).add(kw_s.lower())
                        exact_rules.setdefault(resolved, {})[kw_s] = rep

        for header, mapping in rules_config.get('exact_rules', {}).items():
            resolved = resolve_header(header)
            exact_rules.setdefault(resolved, {}).update(dict(mapping))

        # 收敛策略：若 exact_semantic_clusters 已覆盖某字段，
        # 则自动下线 exact_rules 中与簇“同标签但非簇词”的重复口语短句。
        for header, mapping in list(exact_rules.items()):
            covered_labels = cluster_labels_by_header.get(header, set())
            covered_keywords = cluster_keywords_by_header.get(header, set())
            if not covered_labels:
                continue
            filtered: Dict[str, str] = {}
            for kw, val in mapping.items():
                kw_s = str(kw).strip()
                val_s = str(val).strip()
                if val_s in covered_labels and kw_s.lower() not in covered_keywords:
                    # 由语义簇主导，重复同标签的散点短句不再保留
                    continue
                filtered[kw_s] = val_s
            exact_rules[header] = filtered

        fuzzy_rules: Dict[str, List[Tuple[str, str]]] = {}
        for header, items in rules_config.get('fuzzy_rules', {}).items():
            resolved = resolve_header(header)
            fuzzy_rules.setdefault(resolved, []).extend([(str(p), str(v)) for p, v in items])

        # 语义组结构（可选）：将分组关键词编译为 fuzzy 规则
        semantic_labels_by_header: Dict[str, set[str]] = {}
        for header, groups in rules_config.get("semantic_groups", {}).items():
            resolved = resolve_header(header)
            if not isinstance(groups, dict):
                continue
            for _, group in groups.items():
                if not isinstance(group, dict):
                    continue
                label = str(group.get("label", "")).strip()
                patterns = group.get("patterns", [])
                if not label or not isinstance(patterns, list):
                    continue
                semantic_labels_by_header.setdefault(resolved, set()).add(label)
                safe_patterns = [str(p).strip() for p in patterns if str(p).strip()]
                if not safe_patterns:
                    continue
                merged = "(" + "|".join(safe_patterns) + ")"
                fuzzy_rules.setdefault(resolved, []).append((merged, label))

        # 收敛策略：语义组已覆盖的标签，自动下线同表头 fuzzy 中重复标签项
        # 保留其余 fuzzy 标签作为兜底，避免一次性删除导致召回下降。
        for header, items in list(fuzzy_rules.items()):
            covered_labels = semantic_labels_by_header.get(header, set())
            if not covered_labels:
                continue
            filtered: List[Tuple[str, str]] = []
            seen: set[Tuple[str, str]] = set()
            for pattern, value in items:
                v = str(value).strip()
                p = str(pattern).strip()
                key = (p, v)
                if key in seen:
                    continue
                seen.add(key)
                # 对于 semantic_groups 产出的模式，保留；
                # 对于旧 fuzzy 的同标签模式，下线，交给 semantic_groups 统一维护。
                if v in covered_labels and not (p.startswith("(") and p.endswith(")") and "|" in p):
                    continue
                filtered.append((p, v))
            fuzzy_rules[header] = filtered

        # 从分类规则表补充规则（支持 exact/fuzzy）
        sheet_cols = col_settings.get('category_sheet_columns', {})
        header_col = sheet_cols.get('header_column', '表头')
        keyword_col = sheet_cols.get('keyword_column', '关键词')
        value_col = sheet_cols.get('value_column', '标签值')
        match_type_col = sheet_cols.get('match_type_column', '匹配类型')

        if df_category is None:
            df_category = pd.DataFrame()

        for _, row in df_category.iterrows():
            header = resolve_header(str(row.get(header_col, "")).strip())
            keyword = str(row.get(keyword_col, "")).strip()
            value = str(row.get(value_col, "")).strip() or keyword
            match_type = str(row.get(match_type_col, "exact")).strip().lower()

            if not header or not keyword:
                continue

            if header not in output_columns:
                # 自动兼容规则表里新增的自定义表头
                output_columns.append(header)

            if match_type == "fuzzy":
                fuzzy_rules.setdefault(header, []).append((keyword, value))
            else:
                exact_rules.setdefault(header, {})[keyword] = value

        # 英文关键词兜底映射：支持两种格式
        # 1) {header: {kw: label}}
        # 2) {kw: label}（根据 label 反推 header）
        en_fallback_rules: Dict[str, Dict[str, str]] = {}
        raw_en_map = rules_config.get("en_keyword_to_label_map", {})
        en_map_mode = str(rules_config.get("en_map_mode", "fallback_only")).strip().lower()
        if isinstance(raw_en_map, dict) and en_map_mode == "fallback_only":
            # 构建 value -> header 反查表（优先 exact，再 fuzzy）
            value_to_header: Dict[str, str] = {}
            for h, kv in exact_rules.items():
                for _, v in kv.items():
                    value_to_header.setdefault(str(v).strip(), h)
            for h, items in fuzzy_rules.items():
                for _, v in items:
                    value_to_header.setdefault(str(v).strip(), h)

            # header 嵌套格式
            nested_mode = any(isinstance(v, dict) for v in raw_en_map.values())
            if nested_mode:
                for h, kv in raw_en_map.items():
                    if not isinstance(kv, dict):
                        continue
                    resolved = resolve_header(str(h))
                    if not resolved:
                        continue
                    for kw, val in kv.items():
                        en_fallback_rules.setdefault(resolved, {})[str(kw)] = str(val)
            else:
                for kw, val in raw_en_map.items():
                    resolved = value_to_header.get(str(val).strip(), "")
                    if resolved:
                        en_fallback_rules.setdefault(resolved, {})[str(kw)] = str(val)

        negative_patterns = rules_config.get('negative_patterns', [])
        neutral_patterns = rules_config.get('neutral_patterns', [])
        height_rules = rules_config.get('height_rules', {})
        debug_options = rules_config.get('debug_match', {})
        rule_priority = rules_config.get('rule_priority', ["exact_rules", "fuzzy_rules", "en_keyword_to_label_map"])
        return cls(
            output_columns,
            exact_rules,
            fuzzy_rules,
            en_fallback_rules,
            label_priority_by_header,
            negative_patterns,
            neutral_patterns=neutral_patterns,
            height_rules=height_rules,
            debug_options=debug_options,
            rule_priority=rule_priority,
        )
