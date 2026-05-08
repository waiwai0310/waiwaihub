# 客诉标签分类系统

基于关键词与正则规则的**多列打标**工具：对「评论内容 + 标题」合并清洗后匹配规则，**不再使用一二三级分类**。规则写在配置文件里（可选再用 Excel 规则表扩展）。

**文档：** [快速开始](QUICKSTART.md) · [详细使用指南](USAGE_GUIDE.md)

## 项目结构

```
项目根目录/
├── run.py / main.py     # 入口：python run.py [类目名]
├── config.json          # 默认配置（无参数时使用）
├── config.py            # 配置校验（内含必填通用表头列表）
├── config/              # 多类目时：config/<类目>/config.json
├── data/                # 输入数据（建议按类目分子目录 data/<类目>/）
├── output/              # 输出结果；类目模式为 output/<类目>/
├── classifier.py / data_loader.py / result_saver.py / …
├── QUICKSTART.md / USAGE_GUIDE.md
└── tests/
```

## 多类目（可选）

- 运行 `python run.py <类目>` 时读取 **`config/<类目>/config.json`**，结果写入 **`output/<类目>/`**。
- 数据路径建议在各类目配置中写 **`data/<类目>/xxx.xlsx`**（相对项目根目录）。
- 不带参数时仍使用根目录 **`config.json`**，行为与早期版本一致。
- 若 `log_file`、`output_base_filename` 以 `output/` 开头，类目模式下会自动归到 **`output/<类目>/`**（详见 `main.py`）。
- 文件夹名是中文、命令行想用英文短名时，可在 **`config/_aliases.json`** 里写映射，例如 `{"sofa": "沙发"}`，然后执行 `python run.py sofa`（输出目录仍为 `output/沙发/`）。

## 核心能力

- **多表头输出**：`common_output_columns`（通用）+ `custom_output_columns`（如 `功能标签`）
- **匹配方式**：`exact_rules`（Trie 关键词匹配）+ `fuzzy_rules`（正则，按列表顺序）
- **多标签表头**：`外观标签`、`用户体验标签`、`功能标签` 支持**多条命中**，结果用 **`/`** 连接（同一张文本内同一标签值只出现一次）；其余表头仍为「首条命中即停」
- **英文短语归一**：`rules.en_zh_translation_map` 按**源短语长度降序**处理；**含空格的短语**仍为子串替换，**单个英文词**（可含 `-`/`'`）改为**整词边界**替换，避免 `pet`→competition、`room`→classroom、`office`→officer、`install`→installation 等嵌在更长单词里误替换
- **是否差评**：分类后按 `column_settings.rating_columns` 中的星级列覆盖；`rules.bad_review_max_star`（默认 3）表示「星级 ≤ 该值 → 是」，否则「否」；无法解析星级时为「无」
- **规则来源**：默认仅 JSON 配置；若配置了 `file_settings.category_file` 且文件存在，则从 Excel 追加 exact/fuzzy 规则
- **未命中**：各标签列为空，保存结果时常统一填 **「无」**（见导出逻辑）
- **配置文件编码**：支持 **UTF-8 BOM**（`utf-8-sig` 读取）

## 当前标签体系（与默认配置一致）

### 通用表头

`是否差评`、`外观标签`、`质量标签`、`用户体验标签`、`价格标签`、`安装标签`、`物流标签`、`使用场景标签`、`用户类型`、`使用地点`、`使用目的`、`未满足需求`、`问题类型`、`情绪强度`、`舒适度标签`

### 自定义表头（可按业务增删）

示例：`功能标签`（在 `custom_output_columns` 与 `rules` 中为同名键配置规则即可）

## 快速开始

### 1) 安装依赖

```bash
pip install pandas openpyxl
```

### 2) 配置文件

- **默认**：编辑项目根目录 **`config.json`**。
- **多类目**：使用 **`config/<类目>/config.json`**，并用 `python run.py <类目>` 运行（可从根目录 `config.json` 复制一份再改路径与规则）。

**说明：**

- `description_column` 为 **字符串**（列名）。`title_column` 可选：写出时须为非空列名并与描述列拼接后打标；**整项省略**则只用描述列。列名支持容错别名（见 `data_loader`）。
- **`category_file` 已可选**：不写或留空则只使用 JSON 内规则。
- `file_settings.output_base_filename`：当前校验仍要求该字段非空，**实际写盘路径由输入表文件名生成**（见下文）；模板里可保留任意合法路径占位。
- **`common_output_columns` 必须包含** `config.py` 中 `ConfigManager.COMMON_OUTPUT_COLUMNS` 所列全部通用表头（顺序可自定），否则校验失败。下例为完整列表 + 自定义列示例。

```json
{
    "file_settings": {
        "complaint_file": "data/评论数据.xlsx",
        "output_base_filename": "output/分类结果占位.xlsx",
        "log_file": "output/error_log.txt"
    },
    "column_settings": {
        "description_column": "评论内容/标题",
        "title_column": "标题/评论内容",
        "common_output_columns": [
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
        ],
        "custom_output_columns": ["功能标签"],
        "category_sheet_columns": {
            "header_column": "表头",
            "keyword_column": "关键词",
            "value_column": "标签值",
            "match_type_column": "匹配类型"
        },
        "rating_columns": ["星级", "星级.1"]
    },
    "rules": {
        "prefix_pattern": "^(事件：|问题描述：)+",
        "bad_review_max_star": 3,
        "negative_patterns": ["(投诉|差评|不满意|失望)"],
        "en_zh_translation_map": {
            "sofa bed": "沙发床",
            "price": "价格"
        },
        "exact_rules": {
            "物流标签": { "物流慢": "物流慢" }
        },
        "fuzzy_rules": {
            "质量标签": [["(破损|开裂)", "有缺陷"]]
        }
    }
}
```

可选：再次启用 Excel 规则表时，在 `file_settings` 中增加：

```json
"category_file": "data/你的规则表.xlsx"
```

### 3) 运行

```bash
python run.py
```

多类目（配置在 `config/<类目>/config.json`，结果与日志默认在 `output/<类目>/`）：

```bash
python run.py sofa
```

或直接：

```bash
python main.py
```

（`main.py` 同样支持末尾类目参数，例如 `python main.py sofa`。）

## 输出文件命名

- 默认（根目录 `config.json`）：`output/<客诉文件名（无扩展名）>_分类结果（1）.xlsx`
- 类目模式（`python run.py <类目>`）：`output/<类目>/<客诉文件名（无扩展名）>_分类结果（1）.xlsx`
- 若输入文件名末尾已是 `_分类结果（n）`，会先去掉该后缀再拼，避免重复叠加。
- 若 `（1）` 已存在，则自动递增为 `（2）`、`（3）` …

（`output_base_filename` 不参与上述路径计算，仅满足配置校验；后续版本若统一可再改校验逻辑。）

## 数据要求

### 客诉表（`complaint_file`）

- 必须能解析到 `description_column` 对应列（及配置了 `title_column` 时的该列）。
- 星级列名写在 `rating_columns` 列表中，按顺序取**第一个**在表中存在的列用于覆盖「是否差评」。
- **日期列（可选）**：在 `column_settings` 中配置 `date_normalize`（且 `enabled` 不为 `false`）时，会在分类结束后把 `source_column`（默认 `日期`）中的值解析为统一格式，写入 `output_column`（默认 `日期.1`，如 `YYYY-MM-DD`）。支持中文「2025年4月18日」、Excel 序列日、`datetime` 及常见字符串。
- Excel 中若有多列同名「星级」，pandas 会命名为 `星级`、`星级.1`…，后缀与列名之间为**半角点**（`.`）。配置请写 `星级.1`；若误写 `星级。1` 或 `星级．1`，程序会按列名规范化尽量对齐。

### Excel 规则表（可选，`category_file`）

列需与 `category_sheet_columns` 一致，至少包含：表头、关键词、标签值；可选「匹配类型」`exact` / `fuzzy`。表头不在当前输出列时，程序可能把新表头追加到输出列列表。

## 规则优先级（单个表头内）

### 普通表头（单选）

1. `exact_rules`（Trie **最长**单次匹配，命中即得到该表头结果）
2. 否则 `fuzzy_rules`（正则按列表顺序，**第一条命中即停**）
3. 未命中则该列为空（导出阶段可填「无」）

### 多选表头（`外观标签` / `用户体验标签` / `功能标签`）

逻辑在 `classifier.py` 中固定为上述三个表头名（若自定义列名不同，需改代码中的表头集合）。

1. **精确**：在全文收集所有命中的关键词标签，按**首次出现位置**排序；**相同标签值去重**。
2. **模糊**：再按 `fuzzy_rules` 中该表头的**书写顺序**逐条检测，命中且标签值尚未出现时追加。
3. 最终将标签值用 **`/`** 拼接，例如：`颜色好看/尺寸合适`、`坐感偏硬/螺丝问题`、`USB/舒适`。
4. **互斥后处理**（多选合并前在 `classifier.py` 中处理）：
   - **外观**：`尺寸小/大/合适/错误` 只留一个；**`颜色好看` 与 `颜色不好看`** 只留一个（差评优先）；**`外观好看` 与 `外观不好看`** 只留一个（差评优先）。
   - **用户体验**：**`坐感舒适` / `坐感一般` / `坐感偏硬`** 只留一个（偏硬 > 一般 > 舒适）；**`靠背支撑好` 与 `支撑不够`** 只留一个（支撑不够优先）。
   - **功能标签**：**`垫薄` 与 `厚垫`** 只留一个（垫薄优先，避免又夸厚又嫌薄叠在一起）。

其余表头不受影响。

**是否差评**（概要）：

- 先按分类与 `negative_patterns` 得到一版；
- 再若有可用星级列，按 `bad_review_max_star` **覆盖**为「是/否/无」。

## 否定与子串误匹配（重要）

中文里常见 **否定词（不/没/非…）+ 正面词** 连在一起，若正则里写了很短的正面词（如 `舒服`、`好看`、`方便`、`贵`、`便宜`、`太`、`坐`），会作为**子串**误命中。

**推荐做法（按优先级）：**

1. **否定整句写在前**：在同一表头内，把 `(不舒服|不舒适|不好看|不方便|…)` 整条规则放在含 `舒服|好看|方便` 的正面规则**之前**（单选表头尤其重要）。
2. **固定宽度否定环视**：对仍须保留的短词使用 `(?<![不没])舒服`、`(?<![不没])贵` 等（Python `re` 仅支持**定长** lookbehind，字符类 `[不没]` 算 1 个字符宽）。
3. **多选表头**：`外观标签` 等会合并多条命中，更要在「正面泛化规则」上加环视或先列否定。
4. **情绪类「太」**：`不太好` 里的 `太` 不应触发「强」，可把「中/弱」规则提前，或对「太」使用 `(?<![不没略有点])太`。
5. **译后文本**：英文经 `en_zh_translation_map` 变成中文后，再检查是否出现新的子串碰撞（如 `not comfortable` → `不舒适`）。

新增规则前可自检：是否存在 **「不 / 没 + 你的关键词」** 的常见说法；若有，先写否定分支或环视。

## 维护建议

- 稳定、高频词放 `exact_rules`；表述多变用 `fuzzy_rules`
- 中英混评优先维护 `en_zh_translation_map`（长短语并存时，按 **源短语长度降序** 替换，长条款优先）
- 标签值在团队内归一，避免碎片化
- 未匹配样本可定期抽样，反哺 `fuzzy_rules` / 翻译表

## 常见问题

### 1) 报「客诉表缺少列」

核对 Excel 列名与 `description_column` / `title_column`；或使用与数据一致的别名（程序对部分常用列名做了容错）。

### 2) 不想用 Excel 规则表

删除或不要配置 `category_file` 即可，只维护 JSON 配置（根目录或 `config/<类目>/`）。

### 3) JSON 报错或 BOM

请保存为 UTF-8；带 BOM 也可被正确读取。

### 4)「是否差评」全是「无」

检查是否存在 `rating_columns` 里列名对应的列，以及单元格是否为可解析数字或「x星」类文本。

### 5) 如何新增一列表头

把列名加入 `common_output_columns` 或 `custom_output_columns`，并在 `exact_rules` / `fuzzy_rules` 下使用**同名键**写规则。

### 6) 日志与异常

查看 `file_settings.log_file` 指向的日志文件。使用 `python run.py <类目>` 且原路径为 `output/...` 时，可能被自动改写到 `output/<类目>/` 下。
