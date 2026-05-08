# 快速开始（约 5 分钟）

## 项目结构（与仓库一致）

```
项目根目录/
├── main.py              # 主程序逻辑
├── run.py               # 推荐入口：python run.py
├── config.json          # 配置文件（必改）
├── config.py            # 配置加载与校验
├── classifier.py        # 分类引擎（Trie + 正则）
├── data_loader.py       # 读表与文本清洗
├── result_saver.py      # 写出 Excel
├── logger.py            # 日志
├── ui.py                # 弹窗提示
├── data/                # 建议放输入 xlsx（路径可自定义）
├── output/              # 默认输出目录（程序会尝试创建）
├── config/              # 多类目：config/<类目>/config.json；运行 python run.py <类目>
├── README.md            # 项目说明与规则细节
├── USAGE_GUIDE.md       # 详细使用指南
└── QUICKSTART.md        # 本文件
```

---

## 三步运行

### 1. 安装依赖

```bash
pip install pandas openpyxl
```

### 2. 编辑 `config.json`

在**项目根目录**打开 `config.json`，至少确认：

- `file_settings.complaint_file`：客诉 Excel 路径（相对路径相对项目根目录）。
- `file_settings.output_base_filename`：校验要求非空；**实际输出文件名由输入表名推导**（见 README「输出文件命名」），此处可保留占位路径。
- `file_settings.log_file`：日志路径。
- `column_settings.description_column` / `title_column`：与 Excel 列名一致（程序对部分列名有容错别名）。
- `column_settings.common_output_columns` / `custom_output_columns`：要打出的标签列名。
- `rules.exact_rules` / `rules.fuzzy_rules`：按**输出列名**分组的规则。

`category_file`（Excel 规则表）为**可选**：不配置或留空则仅使用 JSON 内规则。

### 3. 运行

```bash
python run.py
```

多类目（先创建 `config/sofa/config.json`，再运行；结果进 `output/sofa/`）：

```bash
python run.py sofa
```

或直接：

```bash
python main.py
```

（`main.py` 同样支持：`python main.py sofa`。）

---

## 常用配置片段

### 列名与输出列

```json
{
  "column_settings": {
    "description_column": "评论内容/标题",
    "title_column": "标题/评论内容",
    "common_output_columns": ["是否差评", "外观标签", "质量标签"],
    "custom_output_columns": ["功能标签"],
    "rating_columns": ["星级", "星级.1"]
  }
}
```

### 精确关键词（`exact_rules`）

表头名 → 对象：`关键词 → 标签值`（Trie 最长匹配）。

```json
{
  "rules": {
    "exact_rules": {
      "物流标签": {
        "物流慢": "物流慢",
        "发货慢": "物流慢"
      }
    }
  }
}
```

### 正则（`fuzzy_rules`）

表头名 → 数组，每项为 `[ "正则", "标签值" ]`，**按顺序**匹配，普通列**首条命中即停**。

```json
{
  "rules": {
    "fuzzy_rules": {
      "质量标签": [
        ["(破损|开裂|断裂)", "有缺陷"],
        ["(色差|掉色)", "外观瑕疵"]
      ]
    }
  }
}
```

多选列（如 `外观标签`、`用户体验标签`、`功能标签`）的规则合并与互斥逻辑见 `README.md`。

---

## 输出与日志

- **默认**（`python run.py`）：`output/<输入基名>_分类结果（1）.xlsx`，冲突则序号递增。
- **类目模式**（`python run.py <类目>`）：`output/<类目>/<输入基名>_分类结果（1）.xlsx`；以 `output/` 开头的 `log_file`、`output_base_filename` 会自动归到 `output/<类目>/`（若尚未带子路径）。
- 日志路径仍由配置中的 `log_file` 决定（上述自动归集后写入对应目录）。

---

## 故障速查

| 现象 | 处理 |
|------|------|
| 找不到客诉文件 | 检查 `complaint_file` 路径与扩展名 `.xlsx` |
| 报缺少列 | 对照 Excel 修改 `description_column` / `title_column` |
| JSON 报错 | 标准 JSON 不支持注释；可用 [jsonlint.com](https://jsonlint.com/) 校验；保存为 UTF-8（含 BOM 也可） |
| 标签全空或「无」 | 检查 `exact_rules`/`fuzzy_rules` 的键是否与输出列名一致，规则是否覆盖真实话术 |

---

## 文档导航

| 需求 | 文档 |
|------|------|
| 整体设计、优先级、否定与子串 | `README.md` |
| 分节说明与示例代码 | `USAGE_GUIDE.md` |
| 多类目、分 config / data / output 子目录 | `USAGE_GUIDE.md` →「多类目分文件夹管理」 |
| 本页 | `QUICKSTART.md` |

---

## 核心特点（简述）

- 多列表头打标 + Trie 精确匹配 + 正则模糊匹配  
- 评论与标题拼接清洗；可选英译中短语表 `en_zh_translation_map`  
- 星级列可覆盖「是否差评」  
- 规则以 `config.json` 为主，可选 Excel 规则表追加  
