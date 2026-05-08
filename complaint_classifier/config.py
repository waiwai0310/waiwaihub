"""
配置管理模块
负责加载、验证和管理配置文件
"""

import json
import os
from typing import Dict, Tuple, List, Any


class ConfigManager:
    """配置管理器"""
    
    # 默认配置模板
    COMMON_OUTPUT_COLUMNS = [
        "是否差评",
        "外观标签",
        "质量标签",
        "用户体验标签",
        "价格标签",
        "安装标签",
        "物流标签",
        "使用场景标签",
        "用户类型",
        "使用地点",
        "使用目的",
        "未满足需求",
        "问题类型",
        "情绪强度",
        "舒适度标签"
    ]

    DEFAULT_CONFIG = {
        "file_settings": {
            "complaint_file": "data/沙发床用户评价分析-20260409_分类结果（1）.xlsx",
            "output_base_filename": "output/沙发床用户评价分析-20260409_分类结果（1）111.xlsx",
            "log_file": "output/error_log.txt"
        },
        "column_settings": {
            "description_column": "评论内容/标题",
            "title_column": "标题/评论内容",
            "rating_columns": ["星级", "星级.1"],
            "common_output_columns": COMMON_OUTPUT_COLUMNS,
            "custom_output_columns": ["功能", "体验", "画像"],
            "category_sheet_columns": {
                "header_column": "表头",
                "keyword_column": "关键词",
                "value_column": "标签值",
                "match_type_column": "匹配类型"
            },
            "date_normalize": {
                "enabled": False,
                "source_column": "日期",
                "output_column": "日期.1",
                "output_format": "%Y-%m-%d"
            }
        },
        "rules": {
            "prefix_pattern": "^(事件：|退货：|事故：|返回：|回国：|回报：|问题描述：)+",
            "bad_review_max_star": 3,
            "en_zh_translation_map": {
                "sofa bed": "沙发床",
                "comfortable": "舒适",
                "uncomfortable": "不舒适",
                "hard": "偏硬",
                "soft": "柔软",
                "install": "安装",
                "assembly": "组装",
                "broken": "破损",
                "damaged": "损坏",
                "missing parts": "缺件",
                "delivery": "物流",
                "slow shipping": "物流慢",
                "fast shipping": "物流快",
                "expensive": "价格高",
                "cheap": "价格低"
            },
            "negative_patterns": [
                "(投诉|差评|不满意|失望|生气|愤怒|后悔)"
            ],
            "exact_rules": {},
            "fuzzy_rules": {}
        }
    }
    
    def __init__(self, config_path: str):
        """
        初始化配置管理器
        
        Args:
            config_path: 配置文件路径
        """
        self.config_path = config_path
        self.config = None
        self.errors = []
    
    def load(self) -> Tuple[bool, Dict]:
        """
        加载配置文件
        
        Returns:
            (是否成功, 配置字典 或 错误信息)
        """
        # 如果文件不存在，创建模板
        if not os.path.exists(self.config_path):
            self._create_template()
            return False, {"message": "已生成配置模板，请填写后重试"}
        
        # 读取配置文件
        try:
            # 使用 utf-8-sig 兼容带 BOM 的 JSON 文件
            with open(self.config_path, 'r', encoding='utf-8-sig') as f:
                self.config = json.load(f)
        except json.JSONDecodeError as e:
            return False, {"message": f"JSON 格式错误: {e}"}
        except Exception as e:
            return False, {"message": f"读取配置失败: {e}"}
        
        # 验证配置
        is_valid, errors = self.validate()
        if not is_valid:
            return False, {"message": "配置验证失败", "errors": errors}
        
        return True, self.config
    
    def validate(self) -> Tuple[bool, List[str]]:
        """
        验证配置的完整性和正确性
        
        Returns:
            (是否有效, 错误列表)
        """
        if not self.config:
            return False, ["配置未加载"]
        
        errors = []
        
        # 1. 检查顶级结构
        required_keys = ['file_settings', 'column_settings', 'rules']
        for key in required_keys:
            if key not in self.config:
                errors.append(f"缺少配置项: {key}")
        
        if errors:
            return False, errors
        
        # 2. 检查 file_settings
        file_settings = self.config.get('file_settings', {})
        required_files = ['complaint_file', 'output_base_filename', 'log_file']
        for key in required_files:
            if key not in file_settings or not file_settings[key]:
                errors.append(f"file_settings 缺少: {key}")
        
        # 3. 检查 column_settings
        col_settings = self.config.get('column_settings', {})
        required_cols = ['common_output_columns', 'custom_output_columns', 'category_sheet_columns']
        for key in required_cols:
            if key not in col_settings:
                errors.append(f"column_settings 缺少: {key}")

        stc = col_settings.get("source_text_columns")
        has_multi = isinstance(stc, list) and any(
            isinstance(x, str) and str(x).strip() for x in stc
        )
        if has_multi:
            for i, x in enumerate(stc):
                if not isinstance(x, str) or not str(x).strip():
                    errors.append(f"source_text_columns 第 {i + 1} 项须为非空字符串")
        else:
            if (
                "description_column" not in col_settings
                or not str(col_settings.get("description_column", "")).strip()
            ):
                errors.append(
                    "column_settings 缺少有效的 description_column；或使用 source_text_columns 指定多列源文本"
                )

        if "description_column" in col_settings and not str(
            col_settings.get("description_column", "")
        ).strip():
            errors.append("description_column 不能为空字符串")

        if 'title_column' in col_settings and not str(col_settings.get('title_column', '')).strip():
            errors.append("title_column 不能为空字符串")
        if 'rating_columns' in col_settings and not isinstance(col_settings.get('rating_columns'), list):
            errors.append("rating_columns 必须是列表")

        if isinstance(col_settings.get('common_output_columns'), list):
            common_cols = [
                c for c in col_settings['common_output_columns']
                if isinstance(c, str) and str(c).strip()
            ]
            if not common_cols:
                errors.append("common_output_columns 不能为空")
        else:
            errors.append("common_output_columns 必须是列表")

        if not isinstance(col_settings.get('custom_output_columns'), list):
            errors.append("custom_output_columns 必须是列表")

        sheet_cols = col_settings.get('category_sheet_columns', {})
        for key in ['header_column', 'keyword_column', 'value_column']:
            if key not in sheet_cols or not sheet_cols.get(key):
                errors.append(f"category_sheet_columns 缺少: {key}")
        
        # 4. 检查 rules
        rules = self.config.get('rules', {})
        
        # 4.1 检查 prefix_pattern
        if 'prefix_pattern' not in rules:
            errors.append("rules 缺少: prefix_pattern")
        else:
            try:
                import re
                re.compile(rules['prefix_pattern'], re.IGNORECASE)
            except re.error as e:
                errors.append(f"prefix_pattern 正则错误: {e}")
        
        # 4.2 检查 bad_review_max_star
        bad_review_max_star = rules.get('bad_review_max_star', 3)
        try:
            float(bad_review_max_star)
        except (TypeError, ValueError):
            errors.append("rules.bad_review_max_star 必须是数字")

        # 4.3 检查 en_zh_translation_map
        en_zh_translation_map = rules.get('en_zh_translation_map', {})
        if en_zh_translation_map and not isinstance(en_zh_translation_map, dict):
            errors.append("rules.en_zh_translation_map 必须是字典")
        elif isinstance(en_zh_translation_map, dict):
            for k, v in en_zh_translation_map.items():
                if not str(k).strip():
                    errors.append("en_zh_translation_map 存在空key")
                if not str(v).strip():
                    errors.append(f"en_zh_translation_map['{k}'] 的值不能为空")

        # 4.35 检查 zh_translation_map（可选，译后中文优先于 en_zh 应用）
        zh_translation_map = rules.get("zh_translation_map", {})
        if zh_translation_map and not isinstance(zh_translation_map, dict):
            errors.append("rules.zh_translation_map 必须是字典")
        elif isinstance(zh_translation_map, dict):
            for k, v in zh_translation_map.items():
                if not str(k).strip():
                    errors.append("zh_translation_map 存在空key")
                if not str(v).strip():
                    errors.append(f"zh_translation_map['{k}'] 的值不能为空")

        # 4.4 检查 negative_patterns
        negative_patterns = rules.get('negative_patterns', [])
        if not isinstance(negative_patterns, list):
            errors.append("rules.negative_patterns 必须是列表")
        else:
            import re
            for i, pattern in enumerate(negative_patterns):
                try:
                    re.compile(pattern, re.IGNORECASE)
                except re.error as e:
                    errors.append(f"negative_patterns[{i}] 正则错误: {e}")

        # 4.5 检查 exact_rules
        exact_rules = rules.get('exact_rules', {})
        if not isinstance(exact_rules, dict):
            errors.append("rules.exact_rules 必须是字典")
        else:
            for header, mapping in exact_rules.items():
                if not isinstance(mapping, dict):
                    errors.append(f"exact_rules['{header}'] 必须是字典")
                    continue
                for keyword, value in mapping.items():
                    if not str(keyword).strip():
                        errors.append(f"exact_rules['{header}'] 存在空关键词")
                    if not str(value).strip():
                        errors.append(f"exact_rules['{header}']['{keyword}'] 标签值不能为空")

        # 4.6 检查 fuzzy_rules
        fuzzy_rules = rules.get('fuzzy_rules', {})
        if not isinstance(fuzzy_rules, dict):
            errors.append("rules.fuzzy_rules 必须是字典")
        else:
            import re
            for header, items in fuzzy_rules.items():
                if not isinstance(items, list):
                    errors.append(f"fuzzy_rules['{header}'] 必须是列表")
                    continue
                for i, item in enumerate(items):
                    if not isinstance(item, (list, tuple)) or len(item) != 2:
                        errors.append(f"fuzzy_rules['{header}'][{i}] 格式错误，应为 [pattern, value]")
                        continue
                    pattern, value = item
                    if not str(value).strip():
                        errors.append(f"fuzzy_rules['{header}'][{i}] 标签值不能为空")
                    try:
                        re.compile(pattern, re.IGNORECASE)
                    except re.error as e:
                        errors.append(f"fuzzy_rules['{header}'][{i}] 正则错误: {e}")
        
        return len(errors) == 0, errors
    
    def _create_template(self):
        """创建默认配置模板"""
        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self.DEFAULT_CONFIG, f, ensure_ascii=False, indent=4)
            print(f"✅ 已生成配置模板: {self.config_path}")
        except Exception as e:
            print(f"❌ 创建配置模板失败: {e}")
    
    def get(self, key: str, default: Any = None) -> Any:
        """获取配置值"""
        if not self.config:
            return default
        return self.config.get(key, default)
    
    def get_file_settings(self) -> Dict:
        """获取文件设置"""
        return self.config.get('file_settings', {})
    
    def get_column_settings(self) -> Dict:
        """获取列设置"""
        return self.config.get('column_settings', {})
    
    def get_rules(self) -> Dict:
        """获取规则"""
        return self.config.get('rules', {})
