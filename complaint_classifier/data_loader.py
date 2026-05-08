"""
数据加载模块
负责读取 Excel 文件和预处理数据
"""

import glob
import os
import re
from datetime import date, datetime
from typing import Tuple, Optional, Any, List

import pandas as pd

# 中文日期：2025年4月18日、2025年04月18日等
_CN_DATE_RE = re.compile(
    r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*(?:日)?"
)

# en_zh 映射里「单词级」英文 key（可含连字符、撇号），用整词替换，避免 pet→competition、room→classroom、office→officer 等子串误伤
_EN_MAP_TOKEN = re.compile(r"^[a-z0-9'-]+$", re.ASCII)

# 映射 key 若含下列脚本，视为「译后/中文优先」阶段（先于纯西文 key 替换）
_CJK_PRIORITY_IN_KEY = re.compile(
    r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\uac00-\ud7af]"
)


def _translation_key_is_cjk_priority(key: Any) -> bool:
    return bool(_CJK_PRIORITY_IN_KEY.search(str(key)))


def normalize_date_cell(value: Any, output_format: str = "%Y-%m-%d") -> str:
    """
    将单元格中的日期统一为同一字符串格式。
    支持：datetime / date / Timestamp、Excel 序列日、中文「年月日」、YYYYMMDD 整数、常见日期字符串。
    无法解析时返回空字符串。
    """
    if value is None:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    if isinstance(value, (pd.Timestamp, datetime, date)):
        try:
            return pd.Timestamp(value).strftime(output_format)
        except Exception:
            return ""

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        n = float(value)
        if pd.isna(n):
            return ""
        if n == int(n) and 19000101 <= int(n) <= 21001231:
            s8 = f"{int(n):08d}"
            try:
                return datetime.strptime(s8, "%Y%m%d").strftime(output_format)
            except ValueError:
                pass
        if 20000 < n < 200000:
            try:
                ts = pd.Timestamp("1899-12-30") + pd.Timedelta(days=n)
                return ts.strftime(output_format)
            except Exception:
                pass

    s = str(value).strip()
    if not s or s.lower() == "nan":
        return ""

    m = _CN_DATE_RE.search(s)
    if m:
        try:
            y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
            return datetime(y, mo, d).strftime(output_format)
        except ValueError:
            pass

    if re.fullmatch(r"\d+\.?\d*", s):
        try:
            n = float(s)
            if 20000 < n < 200000:
                ts = pd.Timestamp("1899-12-30") + pd.Timedelta(days=n)
                return ts.strftime(output_format)
        except Exception:
            pass

    ts = pd.to_datetime(s, errors="coerce")
    if pd.notna(ts):
        try:
            return pd.Timestamp(ts).strftime(output_format)
        except Exception:
            pass
    return ""


class TextCleaner:
    """
    文本清洗器
    预编译正则表达式，避免重复编译
    """

    @staticmethod
    def _build_translation_steps(translation_map: dict) -> list:
        """将单张映射表转为 (kind, payload, dst) 步骤列表，长短语优先。"""
        steps: list = []
        if not isinstance(translation_map, dict) or not translation_map:
            return steps
        for src, dst in sorted(
            translation_map.items(),
            key=lambda x: len(str(x[0])),
            reverse=True,
        ):
            src_text = str(src).strip().lower()
            dst_text = str(dst).strip()
            if not src_text or not dst_text:
                continue
            if " " in src_text:
                steps.append(("sub", src_text, dst_text))
            elif _EN_MAP_TOKEN.fullmatch(src_text):
                pat = re.compile(r"(?<!\w)" + re.escape(src_text) + r"(?!\w)")
                steps.append(("re", pat, dst_text))
            else:
                steps.append(("sub", src_text, dst_text))
        return steps

    def __init__(
        self,
        prefix_pattern: str,
        translation_map: Optional[dict] = None,
        zh_translation_map: Optional[dict] = None,
    ):
        """
        初始化清洗器
        
        Args:
            prefix_pattern: 要去除的前缀正则模式
            translation_map: 短语映射（通常为 en_zh_translation_map）。key 中含中日韩等字符的项先于 key 为西文的项替换。
            zh_translation_map: 可选；译后中文归一映射，**最先**于 translation_map 应用。
        """
        try:
            self.prefix_re = re.compile(prefix_pattern, re.IGNORECASE)
        except re.error as e:
            print(f"⚠️ 正则表达式错误: {e}")
            self.prefix_re = None
        
        self.space_re = re.compile(r"\s+")
        # 顺序：显式 zh 映射 → en_zh 中含 CJK 的 key → en_zh 中西文 key
        self.translation_steps: list = []
        self.translation_steps.extend(
            self._build_translation_steps(zh_translation_map or {})
        )
        if isinstance(translation_map, dict) and translation_map:
            cjk_keys = {
                k: v
                for k, v in translation_map.items()
                if _translation_key_is_cjk_priority(k)
            }
            latin_keys = {
                k: v
                for k, v in translation_map.items()
                if not _translation_key_is_cjk_priority(k)
            }
            self.translation_steps.extend(self._build_translation_steps(cjk_keys))
            self.translation_steps.extend(self._build_translation_steps(latin_keys))
    
    def clean(self, text: Any) -> str:
        """
        清洗文本：去前缀、转小写、去多余空格
        
        Args:
            text: 原始文本
        
        Returns:
            清洗后的文本
        """
        # 处理空值
        if pd.isna(text):
            return ""
        
        # 转换为字符串并转小写
        text = str(text).lower()

        # 短语翻译归一：先 zh_translation_map 与 key 含 CJK 的项，再西文 key（见 __init__ 说明）
        for kind, payload, dst in self.translation_steps:
            if kind == "sub":
                text = text.replace(payload, dst)
            else:
                text = payload.sub(dst, text)
        
        # 去除前缀
        if self.prefix_re:
            text = self.prefix_re.sub("", text)
        
        # 去除多余空格
        text = self.space_re.sub(" ", text)
        
        return text.strip()


class DataLoader:
    """数据加载器"""
    
    def __init__(self, base_path: str = None):
        """
        初始化数据加载器
        
        Args:
            base_path: 文件基础路径，如果为 None 则使用脚本所在目录
        """
        if base_path is None:
            base_path = os.path.dirname(os.path.abspath(__file__))
        
        self.base_path = base_path

    def _resolved_base_path(self) -> str:
        import sys
        if getattr(sys, "frozen", False):
            return os.path.dirname(sys.executable)
        return self.base_path
    
    def resource_path(self, relative_path: str) -> str:
        """
        获取资源文件的绝对路径
        支持 PyInstaller 打包和正常运行
        
        Args:
            relative_path: 相对路径
        
        Returns:
            绝对路径
        """
        return os.path.normpath(
            os.path.join(self._resolved_base_path(), relative_path.replace("/", os.sep))
        )

    def _scan_data_folders(self, category_folder: Optional[str]) -> list:
        base = self._resolved_base_path()
        folders = [os.path.join(base, "data")]
        if category_folder:
            folders.append(os.path.join(base, "data", category_folder))
        return folders

    def _xlsx_search_hint(self, category_folder: Optional[str]) -> str:
        parts: list = []
        for folder in self._scan_data_folders(category_folder):
            if not os.path.isdir(folder):
                continue
            xs = sorted(glob.glob(os.path.join(folder, "*.xlsx")))
            if xs:
                names = [os.path.basename(x) for x in xs[:12]]
                suf = " …" if len(xs) > 12 else ""
                try:
                    rel = os.path.relpath(folder, self._resolved_base_path())
                except ValueError:
                    rel = folder
                parts.append(f"\n「{rel}」下现有 .xlsx：{', '.join(names)}{suf}")
        if parts:
            parts.append("\n请将文件放入上述目录之一，或修改配置里的路径。")
        else:
            if category_folder:
                parts.append(
                    f"\n未在 data/ 或 data/{category_folder}/ 下发现 .xlsx，"
                    "请放入客诉表或修正 complaint_file。"
                )
            else:
                parts.append("\n未在 data/ 下发现 .xlsx，请放入客诉表或修正 complaint_file。")
        return "".join(parts)

    def _resolve_existing_file(
        self,
        relative_path: str,
        kind: str,
        category_folder: Optional[str] = None,
    ) -> str:
        rel = str(relative_path).strip().replace("\\", "/")
        primary = self.resource_path(rel)
        if os.path.isfile(primary):
            return primary

        if category_folder:
            cf = str(category_folder).strip()
            if rel.startswith("data/"):
                tail = rel[5:]
                alt = os.path.normpath(
                    os.path.join(
                        self._resolved_base_path(), "data", cf, *tail.split("/")
                    )
                )
                if os.path.isfile(alt):
                    print(f"ℹ️ {kind}在类目子目录找到：{alt}")
                    return alt
            base_name = os.path.basename(rel)
            alt2 = os.path.normpath(
                os.path.join(self._resolved_base_path(), "data", cf, base_name)
            )
            if os.path.isfile(alt2):
                print(f"ℹ️ {kind}在类目子目录找到：{alt2}")
                return alt2

        hint = self._xlsx_search_hint(category_folder)
        raise FileNotFoundError(
            f"找不到{kind}。\n"
            f"已尝试：{primary}\n"
            f"配置路径：{rel}"
            f"{hint}"
        )
    
    def load_complaint_data(
        self,
        file_path: str,
        category_folder: Optional[str] = None,
        sheet_name: Any = 0,
    ) -> pd.DataFrame:
        """
        加载客诉数据
        
        Args:
            file_path: 客诉文件路径（相对项目根）
            category_folder: 类目名；配置为 data/xxx 但文件在 data/<类目>/xxx 时会自动尝试
            sheet_name: 工作表名或从 0 起的索引；默认 0。多表文件可在配置 file_settings.complaint_sheet 中指定（如「总表」）。
        
        Returns:
            DataFrame
        
        Raises:
            FileNotFoundError: 文件不存在
            Exception: 文件读取失败
        """
        file_path = self._resolve_existing_file(
            file_path, "客诉表", category_folder
        )
        
        try:
            sn = sheet_name
            if sn is None or (isinstance(sn, str) and not str(sn).strip()):
                sn = 0
            df = pd.read_excel(file_path, sheet_name=sn)
            print(f"✅ 成功加载客诉数据: {len(df)} 行")
            return df
        except Exception as e:
            raise Exception(f"读取客诉文件失败: {e}")
    
    def load_category_data(
        self, file_path: str, category_folder: Optional[str] = None
    ) -> pd.DataFrame:
        """
        加载分类规则数据
        
        Args:
            file_path: 分类文件路径
            category_folder: 类目子目录回退（同 load_complaint_data）
        
        Returns:
            DataFrame
        
        Raises:
            FileNotFoundError: 文件不存在
            Exception: 文件读取失败
        """
        file_path = self._resolve_existing_file(
            file_path, "分类表", category_folder
        )
        
        try:
            df = pd.read_excel(file_path)
            print(f"✅ 成功加载分类规则: {len(df)} 条")
            return df
        except Exception as e:
            raise Exception(f"读取分类文件失败: {e}")

    def _configured_source_text_column_names(self, col_settings: dict) -> List[str]:
        """
        从 column_settings 读取用于拼接打标的源列配置名（已 strip、去空项）。
        优先 source_text_columns；否则退回 description_column + 可选 title_column。
        """
        raw = col_settings.get("source_text_columns")
        if isinstance(raw, list):
            names = [str(x).strip() for x in raw if str(x).strip()]
            if names:
                return names
        desc = str(col_settings.get("description_column", "") or "").strip()
        if not desc:
            return []
        title = str(col_settings.get("title_column", "") or "").strip()
        if title:
            return [desc, title]
        return [desc]

    def resolve_complaint_source_columns(
        self, df: pd.DataFrame, col_settings: dict
    ) -> Tuple[List[str], List[str]]:
        """
        将配置中的列名解析为 DataFrame 中实际存在的列名列表（顺序与配置一致）。

        Returns:
            (resolved_column_names, missing_config_labels)
        """
        desc_fallbacks = [
            "评论内容/标题",
            "标题/评论内容",
            "售后详情",
            "评论内容",
            "标题",
        ]
        title_fallbacks = ["标题/评论内容", "评论内容/标题", "标题", "评论内容"]

        configured = self._configured_source_text_column_names(col_settings)
        if not configured:
            return [], ["（未配置 description_column 或 source_text_columns）"]

        raw = col_settings.get("source_text_columns")
        use_multi = isinstance(raw, list) and any(str(x).strip() for x in raw)

        resolved: List[str] = []
        missing: List[str] = []
        for i, name in enumerate(configured):
            if use_multi:
                r = self._resolve_column_name(df, name, fallback_aliases=[])
            else:
                fb = desc_fallbacks if i == 0 else title_fallbacks
                r = self._resolve_column_name(df, name, fallback_aliases=fb)
            if r:
                resolved.append(r)
            else:
                missing.append(name)
        return resolved, missing

    def validate_columns(
        self,
        df_complaint: pd.DataFrame,
        df_category: pd.DataFrame,
        config: dict
    ) -> Tuple[bool, Optional[str]]:
        """
        验证数据中是否包含所需的列
        
        Args:
            df_complaint: 客诉数据
            df_category: 分类规则数据
            config: 配置字典
        
        Returns:
            (是否有效, 错误信息)
        """
        col_settings = config['column_settings']

        # 检查客诉表（source_text_columns 多列 或 description_column + 可选 title_column）
        _, missing = self.resolve_complaint_source_columns(df_complaint, col_settings)
        if missing:
            return False, "客诉表缺少列: " + ", ".join(missing)
        
        # 检查分类规则表（用于按表头+关键词扩展规则；未配置或空表则跳过）
        if df_category is None or len(df_category) == 0:
            return True, None

        sheet_cols = col_settings.get('category_sheet_columns', {})
        header_col = sheet_cols.get('header_column')
        keyword_col = sheet_cols.get('keyword_column')
        value_col = sheet_cols.get('value_column')
        match_type_col = sheet_cols.get('match_type_column')

        required_rule_cols = [header_col, keyword_col, value_col]
        missing_rule_cols = [col for col in required_rule_cols if col and col not in df_category.columns]
        if missing_rule_cols:
            print(
                f"⚠️ 分类表缺少列: {missing_rule_cols}，将跳过分类表扩展规则，仅使用 config.json 里的规则"
            )

        if match_type_col and match_type_col not in df_category.columns:
            print(f"⚠️ 分类表未找到匹配类型列: '{match_type_col}'，将默认按 exact 处理")
        
        return True, None
    
    def clean_data(
        self,
        df: pd.DataFrame,
        col_settings: dict,
        prefix_pattern: str,
        translation_map: Optional[dict] = None,
        zh_translation_map: Optional[dict] = None,
    ) -> pd.DataFrame:
        """
        清洗数据：按 column_settings 拼接一列或多列源文本后写入 __cleaned_text__。

        Args:
            df: 原始 DataFrame
            col_settings: column_settings 配置（支持 source_text_columns 或 description_column / title_column）
            prefix_pattern: 前缀模式
            translation_map: 短语翻译映射（通常为 en_zh_translation_map；key 含 CJK 的条目先于西文 key 替换）
            zh_translation_map: 可选；rules.zh_translation_map，**最先**替换（译后归一）
        
        Returns:
            清洗后的 DataFrame
        """
        df = df.copy()

        cleaner = TextCleaner(
            prefix_pattern,
            translation_map=translation_map,
            zh_translation_map=zh_translation_map,
        )

        resolved_cols, missing = self.resolve_complaint_source_columns(df, col_settings)
        if missing:
            raise ValueError("找不到用于打标的列: " + ", ".join(missing))

        def _merge_columns(cols: List[str]) -> pd.Series:
            if not cols:
                return pd.Series([""] * len(df), index=df.index, dtype="object")
            merged = df[cols[0]].fillna("").astype(str).str.strip()
            for c in cols[1:]:
                merged = (merged + " " + df[c].fillna("").astype(str).str.strip()).str.strip()
            return merged

        merge_mode = str(col_settings.get("text_merge_mode", "")).strip().lower()
        if merge_mode == "content_priority_title_fallback":
            content_cfg = col_settings.get("content_columns", [])
            title_cfg = col_settings.get("title_fallback_columns", [])

            content_cols: List[str] = []
            for name in content_cfg if isinstance(content_cfg, list) else []:
                resolved = self._resolve_column_name(df, str(name).strip(), fallback_aliases=[])
                if resolved and resolved not in content_cols:
                    content_cols.append(resolved)

            title_cols: List[str] = []
            for name in title_cfg if isinstance(title_cfg, list) else []:
                resolved = self._resolve_column_name(df, str(name).strip(), fallback_aliases=[])
                if resolved and resolved not in title_cols:
                    title_cols.append(resolved)

            if not content_cols:
                # 配置不完整时退回到默认拼接逻辑，避免中断流程
                merged_text = _merge_columns(resolved_cols)
            else:
                content_text = _merge_columns(content_cols)
                title_text = _merge_columns(title_cols)
                merged_text = content_text.where(content_text != "", title_text)
        else:
            merged_text = _merge_columns(resolved_cols)

        df["__cleaned_text__"] = merged_text.apply(cleaner.clean)

        print("✅ 数据清洗完成")

        return df

    def apply_normalized_date_column(
        self,
        df: pd.DataFrame,
        source_column: str,
        output_column: str,
        output_format: str = "%Y-%m-%d",
    ) -> pd.DataFrame:
        """
        从源列解析日期，写入 output_column（覆盖或新建），格式为 output_format。
        """
        resolved = self._resolve_column_name(
            df,
            source_column,
            fallback_aliases=["日期"],
        )
        if not resolved:
            print(f"⚠️ 未找到日期源列「{source_column}」，跳过写入「{output_column}」")
            return df
        out = df.copy()
        out[output_column] = out[resolved].map(
            lambda x: normalize_date_cell(x, output_format)
        )
        print(
            f"✅ 已根据「{resolved}」统一日期格式 →「{output_column}」（{output_format}）"
        )
        return out

    @staticmethod
    def _normalize_col_name(name: Any) -> str:
        """
        标准化列名，用于容错匹配。
        pandas 读 Excel 遇重复列名时为「原名」「原名.1」「原名.2」，间隔符为**半角点**。
        配置里若误写全角点（．）或中文句号（。）+ 数字后缀，会归一成 .1 形式再匹配。
        """
        if name is None:
            return ""
        text = str(name).strip()
        text = text.replace("／", "/").replace("\\", "/")
        # 统一中英文括号，避免「标题（翻译）」与「标题(翻译)」匹配失败
        text = text.replace("（", "(").replace("）", ")")
        text = text.replace(" ", "")
        text = text.replace("．", ".")
        text = re.sub(r"。(\d+)$", r".\1", text)
        return text.lower()

    def _resolve_column_name(
        self,
        df: pd.DataFrame,
        configured_name: str,
        fallback_aliases: list = None
    ) -> Optional[str]:
        """
        根据配置列名和别名，在 DataFrame 中容错查找真实列名
        """
        if fallback_aliases is None:
            fallback_aliases = []

        col_map = {self._normalize_col_name(c): c for c in df.columns}

        # 1) 先按配置值匹配
        key = self._normalize_col_name(configured_name)
        if key in col_map:
            return col_map[key]

        # 2) 再按别名匹配
        for alias in fallback_aliases:
            alias_key = self._normalize_col_name(alias)
            if alias_key in col_map:
                return col_map[alias_key]

        return None
