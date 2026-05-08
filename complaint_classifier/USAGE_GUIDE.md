# 客诉分类系统 — 详细使用指南

## 目录

1. [环境与安装](#环境与安装)
2. [第一次运行](#第一次运行)
3. [多类目：分文件夹管理](#多类目分文件夹管理)
4. [配置项说明](#配置项说明)
5. [规则编写](#规则编写)
6. [Excel 规则表（可选）](#excel-规则表可选)
7. [输出与日志](#输出与日志)
8. [代码中调用（进阶）](#代码中调用进阶)
9. [故障排除](#故障排除)

---

## 环境与安装

### 要求

- Python 3.8+
- 依赖：`pandas`、`openpyxl`

### 安装

```bash
python --version
pip install pandas openpyxl
```

项目为**扁平结构**：`main.py`、`config.json`、`run.py` 等位于**同一项目根目录**。运行前请在根目录执行命令，或保证工作目录与数据文件相对路径一致。

---

## 第一次运行

1. 将客诉表放入 `data/`（或任意路径，在配置里写相对/绝对路径均可）。
2. 编辑根目录下的 `config.json`：至少设置 `complaint_file`、`column_settings`、以及 `rules` 中的 `exact_rules` / `fuzzy_rules`（可与默认模板一致后逐步改）。
3. 执行：

```bash
python run.py
```

控制台会依次打印加载配置、读表、校验、清洗、分类、保存等步骤；成功时通常还有系统弹窗提示输出路径。

---

## 多类目分文件夹管理

推荐目录约定（类目标识用英文或拼音，避免空格与特殊符号）：

```
config/
  sofa/
    config.json       # 沙发类目：完整配置
  phone/
    config.json       # 手机类目
data/
  sofa/               # 沙发类目原始表、规则表等
  phone/
output/
  sofa/               # 沙发类目运行结果、日志（程序自动写入）
  phone/
```

**运行方式（项目根目录）：**

```bash
python run.py sofa
```

- 读取 **`config/<类目>/config.json`**（例：`config/sofa/config.json`）。
- 分类结果写入 **`output/sofa/<输入基名>_分类结果（n）.xlsx`**。
- 若配置里 `log_file`、`output_base_filename` 以 `output/` 开头且尚未包含 `output/sofa/`，程序会自动改成 **`output/sofa/...`**，避免多类目日志/占位路径混在一起。

**仍兼容旧用法：** 不带参数时 `python run.py` 使用根目录 **`config.json`**，结果仍在 **`output/`** 下（不写类目子文件夹）。

**数据路径：** 请在各类目配置里把 `complaint_file`、`category_file` 写成例如 `data/sofa/评论.xlsx`（相对**项目根**）。程序不会自动改写 `data/` 路径，由你按类目分文件夹存放。

**类目名限制：** 命令行类目名不能含 `/`、`\` 或 `..`。新建类目时可从根目录 `config.json` 复制到 `config/<类目>/config.json` 再改路径与规则。

---

## 配置项说明

### `file_settings`

| 字段 | 说明 |
|------|------|
| `complaint_file` | 客诉 Excel，**必填** |
| `category_file` | 规则扩展表，**可选**；省略或空字符串则仅用 JSON |
| `output_base_filename` | 校验要求非空；**当前版本实际输出名由输入文件名生成**，见 README |
| `log_file` | 日志文件路径 |

示例：

```json
{
  "file_settings": {
    "complaint_file": "data/评论数据.xlsx",
    "output_base_filename": "output/占位.xlsx",
    "log_file": "output/error_log.txt"
  }
}
```

### `column_settings`

| 字段 | 说明 |
|------|------|
| `source_text_columns` | **可选。** 字符串数组：按顺序拼接多列原文再打标（列名须与 Excel 一致，不做旧版中文别名容错）。配置此项时**不必**再写 `description_column` / `title_column`。 |
| `description_column` | 主文本列名（与 `title_column` 拼接）；未配置 `source_text_columns` 时**必填**。 |
| `title_column` | 标题列名；**可整项省略**（仅用描述列）。若写出该键则**不能为空字符串** |
| `common_output_columns` | 通用输出标签列名列表 |
| `custom_output_columns` | 自定义标签列（如 `功能标签`） |
| `category_sheet_columns` | Excel 规则表列名映射（启用 `category_file` 时用） |
| `rating_columns` | 星级候选列名，按顺序取第一个存在的列覆盖「是否差评」 |

### `rules`（常用键）

| 键 | 说明 |
|----|------|
| `prefix_pattern` | 去除文首前缀的正则（可选） |
| `zh_translation_map` | **可选。** 译后中文短语 → 归一用词；若配置，**先于** `en_zh_translation_map` 整表替换。 |
| `en_zh_translation_map` | 短语 → 中文归一；**key 中含中日韩字符的条目先于 key 为西文的条目**替换（同一表内自动分两阶段）。 |
| `negative_patterns` | 参与「是否差评」语义判断的正则列表 |
| `bad_review_max_star` | 星级 ≤ 该值视为差评（默认 3） |
| `exact_rules` | 精确匹配：表头 → `{ "关键词": "标签值" }` |
| `fuzzy_rules` | 模糊匹配：表头 → `[ ["正则", "标签值"], ... ]` |

更细的匹配顺序、多选列互斥等见 [README.md](README.md)。

---

## 规则编写

### `exact_rules`（Trie，最长匹配）

- 结构：`"输出列名": { "关键词": "标签值", ... }`
- 同一表头内，文本中命中**最长**关键词时采用对应标签值（单选列则该表头结束）。

```json
"exact_rules": {
  "物流标签": {
    "物流慢": "物流慢",
    "快递慢": "物流慢"
  }
}
```

### `fuzzy_rules`（正则，按顺序）

- 结构：`"输出列名": [ ["模式", "标签值"], ... ]`
- **普通输出列**：第一条命中的 `[模式, 标签值]` 生效即停。
- **多选列**（`外观标签`、`用户体验标签`、`功能标签`）：行为见 README；编写时仍使用同一数组格式。

```json
"fuzzy_rules": {
  "质量标签": [
    ["(破损|开裂|断裂)", "有缺陷"],
    ["(污渍|脏污)", "清洁问题"]
  ]
}
```

### 与 README 一致的建议

- 否定句、短词子串误匹配：否定规则写在正面规则前，或使用定长否定环视 `(?<![不没])…`。
- 稳定高频用语用 `exact_rules`，变体多用 `fuzzy_rules`。

---

## Excel 规则表（可选）

在 `file_settings` 中设置 `category_file` 且文件存在时，会按表扩展规则。

列名由 `category_sheet_columns` 指定，通常包括：

- 表头（对应输出列名）
- 关键词
- 标签值
- 匹配类型（可选）：`exact` / `fuzzy`

若表中缺少必需列，程序会跳过表扩展并仅使用 `config.json` 中的规则（控制台会有提示）。

---

## 输出与日志

- **结果文件**：`output/<输入基名>_分类结果（1）.xlsx`，冲突时序号递增；输入名末尾若已有 `_分类结果（n）` 会先剥离再拼接，避免叠后缀。
- **列内容**：在原始表基础上增加配置的各标签列；未命中导出时可能统一为「无」（见 `result_saver` 逻辑）。
- **日志**：写入 `log_file`，含行数、分类统计（精确 / 模糊 / 默认）等。

---

## 代码中调用（进阶）

以下示例假设**当前工作目录为项目根目录**，或与 `main.py` 同级的脚本内已将根目录加入 `sys.path`（与 `run.py` 做法一致）。

`classify` 返回值为 **`dict`**，键为各输出列名，值为字符串标签（可能为空）。

```python
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

import pandas as pd
from config import ConfigManager
from data_loader import DataLoader
from classifier import ClassifyEngine

config_path = os.path.join(ROOT, "config.json")
cm = ConfigManager(config_path)
ok, cfg = cm.load()
if not ok:
    raise SystemExit(cfg)

loader = DataLoader(ROOT)
df_complaint = loader.load_complaint_data(cfg["file_settings"]["complaint_file"])
cat = str(cfg["file_settings"].get("category_file") or "").strip()
df_cat = loader.load_category_data(cat) if cat else pd.DataFrame()

is_ok, err = loader.validate_columns(df_complaint, df_cat, cfg)
if not is_ok:
    raise RuntimeError(err)

rules = cfg["rules"]
col = cfg["column_settings"]
df_clean = loader.clean_data(
    df_complaint,
    col,
    rules["prefix_pattern"],
    translation_map=rules.get("en_zh_translation_map"),
    zh_translation_map=rules.get("zh_translation_map"),
)

engine = ClassifyEngine.build_from_config(cfg, df_cat)
text = df_clean["__cleaned_text__"].iloc[0]
result = engine.classify(text)
print(result)
```

完整流水线（含星级覆盖「是否差评」、写文件）请以 `main.py` 中 `ComplaintClassifier` 为准。

### 文本清洗单独使用

```python
from data_loader import TextCleaner

cleaner = TextCleaner("^(问题：|事件：)+", translation_map={"sofa bed": "沙发床"})
print(cleaner.clean("问题：物流很慢"))
```

---

## 故障排除

### JSON 无法解析

- 标准 JSON **不能**使用 `//` 注释。
- 检查尾随逗号、引号是否成对。
- 可用 [jsonlint.com](https://jsonlint.com/) 校验。

### 找不到 Excel

- 相对路径相对于**项目根目录**（`DataLoader` 基于代码目录解析资源路径）。
- 文件名需包含扩展名，如 `data/a.xlsx`。

### 客诉表缺少列

- 打开 Excel 核对列名，与 `description_column`、`title_column` 完全一致（或通过程序支持的别名，见 `data_loader.validate_columns`）。

### `prefix_pattern` 报错

- 正则需合法；括号、量词要配对；在 JSON 字符串中反斜杠需写成 `\\`。

### 标签始终为空或「无」

- 确认 `exact_rules` / `fuzzy_rules` 的**外层键**与 `common_output_columns`、`custom_output_columns` 中的列名一致。
- 抽样查看 `__cleaned_text__`（可先跑一遍主流程或在调试里打印）是否被前缀规则或翻译表改得过多。

### 「是否差评」全为「无」

- 检查 `rating_columns` 是否在表存在，单元格是否为数字或可解析的「x星」等格式（解析逻辑见 `main.py` 中 `_extract_star`）。

### 性能

- 规则很多时，优先用 `exact_rules` 承载高频词；避免过于贪婪或回溯过多的正则。

---

## 检查清单

运行前建议确认：

- [ ] Python 与依赖已安装
- [ ] `config.json` 在项目根目录且能通过校验
- [ ] `complaint_file` 路径正确
- [ ] 若使用 Excel 规则表：`category_file` 存在且列名与配置一致
- [ ] 输出列名与规则键名一致

---

## 更多文档

- [README.md](README.md) — 架构、优先级、多选列互斥、否定匹配
- [QUICKSTART.md](QUICKSTART.md) — 最短路径上手
