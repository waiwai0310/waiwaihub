"""
主程序入口
客诉分类系统的主逻辑
"""

import json
import os
import re
import sys
import pandas as pd
import traceback
from typing import Optional

# Windows 控制台默认编码有时是 gbk，遇到 emoji（✅/❌/⚠️ 等）会直接报 UnicodeEncodeError
try:
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True, write_through=True)
    sys.stderr.reconfigure(encoding="utf-8", line_buffering=True, write_through=True)
except Exception:
    # 如果 Python/终端不支持 reconfigure，则继续使用默认编码（可能仍会看到乱码/报错）
    pass

try:
    # 以包方式运行：python -m complaint_classifier.main
    from .config import ConfigManager
    from .classifier import ClassifyEngine
    from .data_loader import DataLoader
    from .result_saver import ResultSaver
    from .logger import Logger
    from .ui import UIManager
except ImportError:
    # 直接运行脚本：python main.py（没有父包时相对导入会失败）
    current_dir = os.path.dirname(__file__)
    if current_dir not in sys.path:
        sys.path.insert(0, current_dir)

    from config import ConfigManager
    from classifier import ClassifyEngine
    from data_loader import DataLoader
    from result_saver import ResultSaver
    from logger import Logger
    from ui import UIManager


def parse_category_arg(raw: Optional[str]) -> Optional[str]:
    """解析命令行类目名；禁止路径分隔符与 ..，避免目录穿越。"""
    if raw is None or not str(raw).strip():
        return None
    s = str(raw).strip()
    for bad in ("/", "\\", ".."):
        if bad in s:
            raise ValueError(f"无效类目名 {raw!r}：禁止包含路径符号或 ..")
    return s


def _load_category_aliases(project_dir: str) -> dict:
    """config/_aliases.json：命令行短名 → 实际子目录名，如 {\"sofa\": \"沙发\"}。"""
    path = os.path.join(project_dir, "config", "_aliases.json")
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def resolve_category_folder(project_dir: str, category_arg: str) -> str:
    """
    将命令行类目参数解析为 config 下的真实文件夹名。
    优先查 config/_aliases.json，否则与文件夹名一致（可用中文等）。
    """
    aliases = _load_category_aliases(project_dir)
    target = aliases.get(category_arg, category_arg)
    if not isinstance(target, str) or not str(target).strip():
        return category_arg
    t = str(target).strip()
    for bad in ("/", "\\", ".."):
        if bad in t:
            raise ValueError(f"别名指向的目录名无效（含禁止字符）：{t!r}")
    return t


def _dirs_with_category_config(project_dir: str) -> list:
    """列出 config/<名>/config.json 已存在的子目录名。"""
    root = os.path.join(project_dir, "config")
    if not os.path.isdir(root):
        return []
    out = []
    for name in sorted(os.listdir(root)):
        if name.startswith("."):
            continue
        if name.endswith(".json"):
            continue
        sub = os.path.join(root, name)
        if os.path.isdir(sub) and os.path.isfile(os.path.join(sub, "config.json")):
            out.append(name)
    return out


def resolve_config_path(project_dir: str, category_folder: Optional[str]) -> str:
    """
    无类目：项目根目录 config.json。
    有类目：config/<文件夹名>/config.json。
    """
    if not category_folder:
        return os.path.join(project_dir, "config.json")
    p = os.path.join(project_dir, "config", category_folder, "config.json")
    if os.path.isfile(p):
        return p
    existing = _dirs_with_category_config(project_dir)
    hint = ""
    if existing:
        hint = "\n当前 config 下已有类目目录（含 config.json）：" + "、".join(existing)
    hint += (
        "\n请使用与文件夹一致的名称运行（如 python run.py 沙发），"
        "或在 config/_aliases.json 中配置短名映射，例如 {\"sofa\": \"沙发\"}。"
    )
    raise FileNotFoundError(
        f"类目配置不存在：{p}{hint}"
    )


class ComplaintClassifier:
    """客诉分类系统主类"""
    
    def __init__(self, config_path: str, category_id: Optional[str] = None):
        """
        初始化分类系统
        
        Args:
            config_path: 配置文件路径
            category_id: 类目标识；非空时结果写入 output/<类目>/，并调整部分 output/ 相对路径
        """
        self.config_manager = ConfigManager(config_path)
        self.category_id = category_id
        self.logger = None
        self.config = None
    
    def run(self) -> bool:
        """
        运行主程序
        
        Returns:
            是否成功
        """
        try:
            print("=" * 60)
            print("客诉分类系统 v2.0")
            print("=" * 60)
            
            # 1. 加载配置
            print("\n【第 1 步】加载配置...")
            success, config_or_error = self.config_manager.load()
            
            if not success:
                error_msg = config_or_error.get('message', '未知错误')
                if 'errors' in config_or_error:
                    error_msg += "\n" + "\n".join(config_or_error['errors'])
                UIManager.show_error("配置错误", error_msg)
                return False
            
            self.config = config_or_error
            print("✅ 配置加载成功")
            if self.category_id:
                print(f"   类目：{self.category_id}")
            print(f"   配置：{self.config_manager.config_path}")

            self._apply_category_file_settings()

            # 运行前确保项目目录下存在 data/、output/ 及类目子目录
            project_dir = os.path.dirname(os.path.abspath(__file__))
            os.makedirs(os.path.join(project_dir, "data"), exist_ok=True)
            os.makedirs(os.path.join(project_dir, "output"), exist_ok=True)
            if self.category_id:
                os.makedirs(
                    os.path.join(project_dir, "data", self.category_id),
                    exist_ok=True,
                )
                os.makedirs(
                    os.path.join(project_dir, "output", self.category_id),
                    exist_ok=True,
                )
            
            # 初始化日志
            log_file = self.config['file_settings']['log_file']
            self.logger = Logger(log_file)
            self.logger.info(f"程序启动，配置文件：{self.config_manager.config_path}")
            
            # 2. 加载数据
            print("\n【第 2 步】加载数据...")
            df_complaint, df_category = self._load_data()
            
            # 3. 验证数据
            print("\n【第 3 步】验证数据...")
            self._validate_data(df_complaint, df_category)
            
            # 4. 清洗数据
            print("\n【第 4 步】清洗数据...")
            df_complaint = self._clean_data(df_complaint)
            
            # 5. 构建分类器
            print("\n【第 5 步】构建分类器...")
            classifier = self._build_classifier(df_category)
            
            # 6. 执行分类
            print("\n【第 6 步】执行分类...")
            df_complaint = self._classify(df_complaint, classifier)
            df_complaint = self._apply_date_normalize(df_complaint)
            
            # 7. 保存结果
            print("\n【第 7 步】保存结果...")
            output_path = self._save_result(df_complaint)
            
            # 8. 显示摘要
            print("\n【第 8 步】生成摘要...")
            self._show_summary(df_complaint, classifier, output_path)
            
            print("\n" + "=" * 60)
            print("✅ 任务完成")
            print("=" * 60)
            
            # 显示成功弹窗
            file_size = ResultSaver().get_output_size(output_path)
            UIManager.show_info(
                "成功",
                f"✅ 分类完成！\n\n已生成文件：\n{output_path}\n文件大小：{file_size}"
            )
            
            return True
        
        except Exception as e:
            self._handle_error(e)
            return False
    
    def _load_data(self) -> tuple:
        """加载数据文件"""
        try:
            loader = DataLoader()
            
            file_settings = self.config['file_settings']
            complaint_file = file_settings['complaint_file']
            category_file = str(file_settings.get('category_file', '') or '').strip()
            
            complaint_sheet = file_settings.get("complaint_sheet", 0)
            df_complaint = loader.load_complaint_data(
                complaint_file, self.category_id, sheet_name=complaint_sheet
            )
            if category_file:
                df_category = loader.load_category_data(
                    category_file, self.category_id
                )
            else:
                df_category = pd.DataFrame()
                print("ℹ️ 未配置 category_file，仅使用 config.json 中的规则")
            
            self.logger.info(f"客诉数据：{len(df_complaint)} 行")
            self.logger.info(
                f"分类规则表：{len(df_category)} 条（Excel）；config.json 规则始终生效"
            )
            
            return df_complaint, df_category
        
        except FileNotFoundError as e:
            self.logger.error(f"文件不存在：{e}")
            raise
        except Exception as e:
            self.logger.error(f"加载数据失败：{e}")
            raise
    
    def _validate_data(self, df_complaint: pd.DataFrame, df_category: pd.DataFrame):
        """验证数据"""
        try:
            loader = DataLoader()
            is_valid, error_msg = loader.validate_columns(df_complaint, df_category, self.config)
            
            if not is_valid:
                raise ValueError(error_msg)
            
            print("✅ 数据验证成功")
        
        except Exception as e:
            self.logger.error(f"数据验证失败：{e}")
            raise
    
    def _clean_data(self, df_complaint: pd.DataFrame) -> pd.DataFrame:
        """清洗数据"""
        try:
            loader = DataLoader()
            
            col_settings = self.config['column_settings']
            rules = self.config['rules']
            
            prefix_pattern = rules['prefix_pattern']
            translation_map = rules.get('en_zh_translation_map', {})
            zh_translation_map = rules.get('zh_translation_map', {})

            df = loader.clean_data(
                df_complaint,
                col_settings,
                prefix_pattern,
                translation_map=translation_map,
                zh_translation_map=zh_translation_map,
            )
            
            return df
        
        except Exception as e:
            self.logger.error(f"数据清洗失败：{e}")
            raise

    def _apply_date_normalize(self, df: pd.DataFrame) -> pd.DataFrame:
        """按 column_settings.date_normalize 将源列日期统一写入目标列（如 日期.1）。"""
        dn = self.config.get("column_settings", {}).get("date_normalize")
        if not isinstance(dn, dict):
            return df
        if dn.get("enabled") is False:
            return df
        src = str(dn.get("source_column", "日期")).strip() or "日期"
        tgt = str(dn.get("output_column", "日期.1")).strip() or "日期.1"
        fmt = str(dn.get("output_format", "%Y-%m-%d")).strip() or "%Y-%m-%d"
        loader = DataLoader()
        return loader.apply_normalized_date_column(df, src, tgt, fmt)
    
    def _build_classifier(self, df_category: pd.DataFrame) -> ClassifyEngine:
        """构建分类器"""
        try:
            classifier = ClassifyEngine.build_from_config(self.config, df_category)
            self.logger.info("分类器构建成功")
            return classifier
        
        except Exception as e:
            self.logger.error(f"构建分类器失败：{e}")
            raise
    
    def _classify(self, df: pd.DataFrame, classifier: ClassifyEngine) -> pd.DataFrame:
        """执行分类"""
        try:
            df = df.copy()

            # 对清洗后的文本应用分类逻辑，输出为多表头标签
            result_df = df['__cleaned_text__'].apply(
                lambda x: pd.Series(classifier.classify(x))
            )
            for col in result_df.columns:
                df[col] = result_df[col]

            # 按星级覆盖「是否差评」（仅当输出列包含该表头时）
            if "是否差评" in result_df.columns:
                rating_columns = self.config['column_settings'].get(
                    "rating_columns", ["星级", "星级.1"]
                )
                bad_review_max_star = float(self.config['rules'].get("bad_review_max_star", 3))
                rating_col = self._resolve_rating_column(df, rating_columns)
                if rating_col:
                    df["是否差评"] = df[rating_col].apply(
                        lambda x: self._is_bad_review_by_rating(x, bad_review_max_star)
                    )
                    self.logger.info(
                        f"是否差评按星级列计算：{rating_col}，阈值<= {bad_review_max_star}"
                    )
                else:
                    self.logger.warning("未找到可用星级列，是否差评保留规则匹配结果")
            
            # 记录统计信息
            stats = classifier.get_stats()
            self.logger.info(
                f"分类统计 - 精确匹配：{stats['exact']}，模糊匹配：{stats['fuzzy']}，默认：{stats['default']}"
            )
            
            print(f"✅ 分类完成，共处理 {len(df)} 条数据")
            
            return df
        
        except Exception as e:
            self.logger.error(f"分类执行失败：{e}")
            raise

    @staticmethod
    def _resolve_rating_column(df: pd.DataFrame, candidates) -> Optional[str]:
        """从候选列表中找第一个存在的星级列（列名规范化与 data_loader 一致，支持 .1 后缀格式）。"""
        if not isinstance(candidates, list):
            return None
        normalized = {DataLoader._normalize_col_name(c): c for c in df.columns}
        for name in candidates:
            key = DataLoader._normalize_col_name(name)
            if key in normalized:
                return normalized[key]
        return None

    @staticmethod
    def _extract_star(value) -> Optional[float]:
        """从星级文本中提取数值星级"""
        if pd.isna(value):
            return None
        text = str(value).strip().lower()
        if not text or text == "nan":
            return None

        # 1) 数字优先，如 4 / 4.0 / 4星 / 4 stars
        m = re.search(r"(\d+(?:\.\d+)?)", text)
        if m:
            try:
                return float(m.group(1))
            except ValueError:
                pass

        # 2) 星星符号计数
        if "⭐" in text:
            return float(text.count("⭐"))
        if "*" in text:
            return float(text.count("*"))

        # 3) 中文一二三四五星
        cn_map = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5}
        m_cn = re.search(r"([一二三四五])星", text)
        if m_cn:
            return float(cn_map[m_cn.group(1)])

        # 4) 差评/中评/好评
        if "差评" in text:
            return 1.0
        if "中评" in text:
            return 3.0
        if "好评" in text:
            return 5.0
        return None

    def _is_bad_review_by_rating(self, value, bad_review_max_star: float) -> str:
        """根据星级计算是否差评"""
        star = self._extract_star(value)
        if star is None:
            return "无"
        return "是" if star <= bad_review_max_star else "否"

    def _apply_category_file_settings(self) -> None:
        """
        类目模式下，将仍以 output/ 开头的 log_file、output_base_filename
        归到 output/<类目>/ 下（若尚未带该类目前缀）。
        """
        if not self.category_id:
            return
        fs = self.config.get("file_settings", {})
        cat_prefix = f"output/{self.category_id}/"
        for key in ("log_file", "output_base_filename"):
            if key not in fs:
                continue
            val = str(fs.get(key, "")).strip().replace("\\", "/")
            if not val:
                continue
            if val.startswith("output/") and not val.startswith(cat_prefix):
                rest = val[len("output/") :].lstrip("/")
                fs[key] = cat_prefix + rest
    
    def _save_result(self, df: pd.DataFrame) -> str:
        """保存结果"""
        try:
            file_settings = self.config['file_settings']
            complaint_file = file_settings.get('complaint_file', '')
            complaint_name = os.path.splitext(os.path.basename(complaint_file))[0]
            # 清理输入名中已有的“_分类结果（x）”后缀，避免重复叠加
            complaint_name = re.sub(r"_分类结果（\d+）$", "", complaint_name)
            if self.category_id:
                output_filename = (
                    f"output/{self.category_id}/{complaint_name}_分类结果（1）.xlsx"
                )
            else:
                output_filename = f"output/{complaint_name}_分类结果（1）.xlsx"
            
            saver = ResultSaver()
            output_path = saver.save_result(
                df,
                output_filename,
                column_groups=self._build_column_groups(df.columns.tolist()),
            )
            
            self.logger.info(f"结果已保存：{output_path}")
            
            return output_path
        
        except Exception as e:
            self.logger.error(f"保存结果失败：{e}")
            raise

    @staticmethod
    def _build_column_groups(current_columns: list) -> list:
        """
        构建导出首行分组标签（如 1. 使用人群（Who））。
        仅对当前存在的列生效。
        """
        groups = [
            ("1. 使用人群（Who）", ["宠物友好", "儿童安全", "过敏人群", "低维护友好"]),
            ("2. 使用时间（When）", ["节日装饰", "季节适配"]),
            ("3. 使用场景（Where）", ["客厅装饰", "卧室装饰", "商业空间", "阳台/庭院", "场景类型"]),
            ("4. 核心问题（Pain Point）", ["核心痛点"]),
            ("5. 购买动机（Motivation）", ["购买动机", "婚礼/活动"]),
            ("6. 核心结果（Functional Outcome）", ["真实度/仿真度", "颜色自然度", "枝叶茂密度", "尺寸/高度", "可塑性/造型"]),
            ("7. 外观与做工（Design & Craft）", ["叶子质感", "树干质感", "材质评价", "做工质量"]),
            ("8. 使用体验（UX）", ["组装难度", "稳定性/底座", "防尘/清洁"]),
            ("9. 质量&交易（Risk & Value）", ["耐用性/品控", "气味", "霉菌", "包装保护", "售后体验", "性价比"]),
        ]
        existing = set(current_columns)
        return [(label, [c for c in cols if c in existing]) for label, cols in groups]
    
    def _show_summary(self, df: pd.DataFrame, classifier: ClassifyEngine, output_path: str):
        """显示摘要"""
        try:
            stats = classifier.get_stats()
            
            summary_text = f"""
处理统计：
  总数据行：{len(df)}
  精确匹配：{stats['exact']} 条
  模糊匹配：{stats['fuzzy']} 条
  默认分类：{stats['default']} 条

输出文件：
  {output_path}
            """
            
            print(summary_text)
            self.logger.info("处理完成")
        
        except Exception as e:
            self.logger.warning(f"生成摘要失败：{e}")
    
    def _handle_error(self, error: Exception):
        """处理错误"""
        error_msg = traceback.format_exc()
        
        # 写入日志
        if self.logger:
            self.logger.error(error_msg)
            self.logger.flush()
        
        print(f"\n❌ 发生错误：{str(error)}")
        print(f"详情请查看日志文件：{self.config['file_settings']['log_file'] if self.config else 'error_log.txt'}")
        
        UIManager.show_error(
            "执行错误",
            f"❌ 执行过程中出错：\n\n{str(error)}\n\n详情请查看日志文件。"
        )


def main(argv=None):
    """主函数。可选参数：python run.py <类目> → 读取 config/<类目>/config.json；
    python run.py pivot [分类结果.xlsx | 类目] → 透视（无参则取 output 下最新）。"""
    argv = argv if argv is not None else sys.argv
    project_dir = os.path.dirname(os.path.abspath(__file__))

    if len(argv) > 1 and str(argv[1]).strip().lower() == "pivot":
        from pivot_tool import run_pivot_cli, try_resolve_pivot_input_as_xlsx

        pivot_args = [str(a).strip() for a in argv[2:] if str(a).strip()]
        try:
            if len(pivot_args) > 1:
                raise ValueError(
                    "pivot 至多接受一个参数：分类结果 .xlsx 路径，或类目名（如 沙发）。\n"
                    "示例：python run.py pivot\n"
                    "      python run.py pivot output/沙发/xxx_分类结果（1）.xlsx\n"
                    "      python run.py pivot 沙发"
                )
            explicit: Optional[str] = None
            category_folder: Optional[str] = None
            if not pivot_args:
                pass
            else:
                token = pivot_args[0]
                explicit = try_resolve_pivot_input_as_xlsx(project_dir, token)
                if explicit is None:
                    if token.lower().endswith(".xlsx"):
                        raise FileNotFoundError(
                            f"未找到指定的 Excel：{token!r}\n"
                            f"已尝试：相对工程目录、相对当前工作目录解析。"
                        )
                    cat = parse_category_arg(token)
                    if cat:
                        try:
                            category_folder = resolve_category_folder(project_dir, cat)
                        except ValueError as e:
                            print(f"❌ {e}")
                            sys.exit(1)
            run_pivot_cli(project_dir, source_xlsx=explicit, category_id=category_folder)
        except ValueError as e:
            print(f"❌ {e}")
            sys.exit(1)
        except FileNotFoundError as e:
            print(f"❌ {e}")
            sys.exit(1)
        except Exception as e:
            print(f"❌ 透视失败：{e}")
            traceback.print_exc()
            sys.exit(1)
        sys.exit(0)

    try:
        category_arg = parse_category_arg(argv[1] if len(argv) > 1 else None)
    except ValueError as e:
        print(f"❌ {e}")
        sys.exit(1)
    category_folder = None
    if category_arg:
        try:
            category_folder = resolve_category_folder(project_dir, category_arg)
        except ValueError as e:
            print(f"❌ {e}")
            sys.exit(1)
    try:
        config_path = resolve_config_path(project_dir, category_folder)
    except FileNotFoundError as e:
        print(f"❌ {e}")
        sys.exit(1)

    classifier = ComplaintClassifier(config_path, category_id=category_folder)
    success = classifier.run()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
