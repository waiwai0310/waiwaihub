# Amazon产品数据爬虫使用说明

## 功能概述

本工具可以爬取Amazon产品的详细数据并输出到Excel表格，包含以下维度：

### 基本信息
- **ASIN**: 产品唯一标识
- **首图**: 主图URL
- **品牌**: 产品品牌
- **标题**: 产品标题
- **链接**: 产品页面URL

### 价格与评价
- **价格**: 当前价格
- **活动优惠价**: 促销价格（如有）
- **评分**: 用户评分（1-5星）
- **评论数**: 评论总数

### 排名信息
- **BSR排名**: Best Sellers Rank总排名
- **大类**: 主类目名称
- **大类排名**: 主类目中的排名
- **小类**: 子类目名称
- **小类排名**: 子类目中的排名

### 产品属性
- **上架时间**: 产品首次上架日期
- **变体数量**: 可选变体数量（颜色、尺寸等）
- **畅销颜色**: 最受欢迎的颜色选项

### 销售数据（需要第三方工具）
- **近30天月销量**: 最近30天的销售量
- **最好的月销**: 历史最佳月销量

### 产品卖点
- **卖点1-5**: 产品的主要特点和优势

## 安装依赖

```bash
pip install -r requirements.txt
```

如果需要使用Playwright（推荐，用于获取完整页面）：

```bash
playwright install chromium
```

## 使用方法

### 1. 爬取单个产品

```bash
python crawl_product_data.py -a B0DDTCQGTR
```

### 2. 爬取多个产品

```bash
python crawl_product_data.py -a B08N5WRWNW B07XJ8C8F5 B09G9FPHY6
```

### 3. 从文件读取ASIN列表

创建一个文本文件（如 `asin_list.txt`），每行一个ASIN：
```
B08N5WRWNW
B07XJ8C8F5
B09G9FPHY6
```

然后运行：
```bash
python crawl_product_data.py -f asin_list.txt
```

### 4. 指定输出文件名

```bash
python crawl_product_data.py -f asin_list.txt -o 沙发产品数据.xlsx
```

### 5. 指定Amazon域名

```bash
# 日本站
python crawl_product_data.py -a B08N5WRWNW -d jp

# 英国站
python crawl_product_data.py -a B08N5WRWNW -d uk
```

支持的域名：us, uk, de, fr, es, it, jp, ca, mx, au, in, br

### 6. 指定输出目录

```bash
python crawl_product_data.py -f asin_list.txt --output-dir /path/to/output
```

### 7. 不生成汇总统计

```bash
python crawl_product_data.py -f asin_list.txt --no-summary
```

## 输出格式

爬取完成后，会生成一个Excel文件，包含两个sheet：

### Sheet 1: Summary（汇总统计）
- 爬取时间
- 总产品数
- 成功/失败数量
- 各字段完整度统计

### Sheet 2: Products（产品数据）
包含所有爬取的产品数据，每个产品一行

## 注意事项

### 1. 反爬虫机制
Amazon有严格的反爬虫机制，建议：
- 不要频繁爬取（已内置2秒延迟）
- 使用Playwright模拟真实浏览器
- 遇到验证码时手动完成验证

### 2. 数据完整性
某些字段可能无法获取：
- **近30天月销量**和**最好的月销**：需要第三方工具（如Keepa、Jungle Scout）
- **畅销颜色**：如果产品没有颜色变体则为空
- **促销价格**：只在有促销活动时显示

### 3. 性能考虑
- 使用Playwright会比纯requests慢，但能获取更完整的数据
- 大批量爬取建议分批处理
- 可以使用 `--skip-existing` 跳过已下载的产品（需要数据库支持）

## 常见问题

### Q: 提示"遭遇验证码拦截"怎么办？
A: 这是正常现象。使用Playwright时，浏览器会弹出，请在弹出窗口中完成验证。验证通过后，会话状态会被保存，后续爬取不需要再次验证。

### Q: 某些字段数据为空？
A: 可能的原因：
1. Amazon页面结构变化（需要更新解析器）
2. 该产品确实没有这个数据（如没有促销价）
3. 页面未完全加载（尝试使用Playwright）

### Q: 如何获取销售量数据？
A: 销售量数据Amazon不公开，需要使用第三方工具如：
- Keepa (https://keepa.com)
- Jungle Scout
- Helium 10

这些工具通常提供API，可以与本爬虫集成。

## 进阶使用

### 与图片爬虫结合

可以先爬取产品数据，然后根据Excel中的ASIN批量下载图片：

```bash
# 1. 爬取产品数据
python crawl_product_data.py -f asin_list.txt -o products.xlsx

# 2. 提取ASIN列表（从Excel中）
# 假设ASIN在第一列，可以用pandas提取

# 3. 下载图片
python main.py -f asin_list.txt
```

### 定制化开发

如果需要添加其他字段，可以修改 `product_data_crawler.py` 中的提取方法，并在 `excel_exporter.py` 中添加对应的列定义。

## 项目结构

```
image_data/
├── crawl_product_data.py       # 产品数据爬取主程序
├── product_data_crawler.py     # 产品数据爬取器
├── excel_exporter.py           # Excel导出器
├── main.py                     # 图片下载主程序（原有功能）
├── image_downloader.py         # 图片下载器
├── request_manager.py          # HTTP请求管理器
├── database.py                 # 数据库管理器
├── config.py                   # 配置文件
├── requirements.txt            # Python依赖
├── data/                       # 输出目录
│   ├── images/                 # 图片存储
│   └── *.xlsx                  # Excel文件
└── logs/                       # 日志目录
```

## 许可证

本工具仅供学习和研究使用。使用时请遵守Amazon的服务条款和robots.txt规则。
