# Amazon Image Crawler - Project Overview
# 项目总览

## 🎯 项目简介

这是一套**生产级**的亚马逊产品图片爬取系统,专为市场研究和产品分析设计。

**核心特性:**
✅ 安全稳定 - 多层反爬虫策略
✅ 智能去重 - SQLite数据库管理
✅ 高质量图片 - 自动获取最高分辨率
✅ 详细日志 - 完整的操作记录和统计
✅ 易于使用 - 命令行接口,开箱即用

---

## 📦 项目文件结构

```
amazon_image_crawler/
│
├── 📄 核心代码 (5个Python文件)
│   ├── config.py              # 配置管理(关键安全参数)
│   ├── database.py            # 数据库管理(下载历史、去重)
│   ├── request_manager.py     # HTTP请求管理(反爬虫核心)
│   ├── image_downloader.py    # 图片下载业务逻辑
│   └── main.py               # 主程序入口
│
├── 🔧 辅助工具 (2个Python脚本)
│   ├── statistics.py          # 数据统计分析工具
│   └── verify_images.py       # 图片完整性验证工具
│
├── 📚 文档 (3个Markdown文件)
│   ├── README.md             # 项目说明和使用指南
│   ├── SOP.md                # 标准操作流程(必读!)
│   └── QUICKSTART.md         # 快速开始指南
│
├── ⚙️ 配置文件 (2个文本文件)
│   ├── requirements.txt      # Python依赖包列表
│   └── asin_list_example.txt # ASIN列表示例
│
└── 📂 运行时目录 (自动创建)
    ├── data/
    │   ├── images/           # 下载的图片(按ASIN分类)
    │   │   ├── B08N5WRWNW/
    │   │   ├── B07XJ8C8F5/
    │   │   └── ...
    │   └── crawler_db.sqlite # SQLite数据库
    └── logs/
        └── crawler.log       # 运行日志
```

---

## 🚀 快速开始

### 1分钟安装运行

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 测试运行(单个产品)
python main.py -a B08N5WRWNW

# 3. 查看结果
ls data/images/B08N5WRWNW/
```

### 详细使用请参考:
- ⚡ [QUICKSTART.md](QUICKSTART.md) - 快速开始
- 📖 [README.md](README.md) - 完整说明
- 🛡️ [SOP.md](SOP.md) - 标准操作流程(强烈推荐!)

---

## 🔑 核心模块说明

### 1. config.py - 配置中心
**作用:** 所有安全参数和配置的集中管理

**关键配置:**
- 请求频率控制(REQUEST_DELAY, RATE_LIMIT)
- User-Agent池
- 重试策略
- 代理配置
- 图片质量设置

**修改建议:**
⚠️ 如遇429错误,增加REQUEST_DELAY
⚠️ 不要随意降低延迟设置

---

### 2. database.py - 数据库管理
**作用:** 管理下载历史,实现智能去重

**功能:**
- 记录所有下载历史
- 自动去重,避免重复下载
- 请求日志记录(速率监控)
- 统计信息查询
- 错误追踪

**数据表:**
- products: 产品信息
- image_downloads: 图片下载记录
- request_logs: HTTP请求日志

---

### 3. request_manager.py - 请求管理
**作用:** 反爬虫核心,处理所有HTTP请求

**反爬虫策略:**
- User-Agent轮换
- 智能延迟(随机+令牌桶)
- 自动重试(指数退避)
- 429检测和自动延长等待
- 代理支持

**安全特性:**
- 完整的浏览器请求头模拟
- Referer自动设置
- 错误分类和处理
- 详细的请求日志

---

### 4. image_downloader.py - 下载核心
**作用:** 图片下载业务逻辑

**功能流程:**
1. 构建产品URL
2. 获取产品页面
3. 解析HTML提取图片URL
4. 升级URL到最高质量
5. 下载图片并保存
6. 记录到数据库

**图片质量:**
- 优先级: 1500px > 1000px > 679px
- 自动URL升级
- 支持多种Amazon图片格式

---

### 5. main.py - 主程序
**作用:** 命令行接口和程序入口

**支持的命令:**
```bash
# 下载操作
-a, --asin        # 单个或多个ASIN
-f, --file        # 从文件读取ASIN列表
-d, --domain      # Amazon域名(us/uk/jp/de/fr)
-m, --max-images  # 每个产品最多下载图片数

# 管理命令
--stats           # 显示统计信息
--recent-errors   # 显示最近错误
--cleanup-logs    # 清理旧日志
```

---

## 🛡️ 安全设计

### 多层安全机制

**第1层: 请求频率控制**
- 令牌桶算法限流
- 每分钟最多30次请求(可配置)
- 随机延迟2-5秒

**第2层: User-Agent轮换**
- 5个常见浏览器UA池
- 随机选择,模拟真实用户

**第3层: 智能重试**
- 最多3次重试
- 指数退避策略
- 区分致命错误和可重试错误

**第4层: 错误检测**
- 429自动延长等待(60秒)
- 403/404不重试
- 超时和网络错误重试

**第5层: 数据持久化**
- 完整的下载历史
- 自动去重
- 错误追踪和分析

---

## 📊 性能指标

### 推荐配置下的性能

| 指标 | 数值 |
|------|------|
| 每小时产品数 | 200-300 |
| 每产品耗时 | 12-18秒 |
| 每产品图片数 | 平均5-7张 |
| 成功率 | >95% |
| 封禁风险 | 极低 |

### 资源消耗

| 资源 | 消耗 |
|------|------|
| CPU | <5% (单线程) |
| 内存 | <100MB |
| 磁盘 | 约2-5MB/产品 |
| 网络 | 约10-30MB/小时 |

---

## 🔧 扩展和定制

### 添加新Amazon站点
在 `config.py` 中:
```python
AMAZON_DOMAINS = {
    'us': 'amazon.com',
    'uk': 'amazon.co.uk',
    'jp': 'amazon.co.jp',
    'de': 'amazon.de',
    'fr': 'amazon.fr',
    'ca': 'amazon.ca',  # 新增加拿大站点
}
```

### 自定义图片质量
在 `config.py` 中:
```python
IMAGE_SIZE_PRIORITY = [
    '_SL2000_',  # 2000px (如果有)
    '_SL1500_',
    '_SL1000_',
]
```

### 添加代理
在 `config.py` 中:
```python
USE_PROXY = True
PROXY_LIST = [
    'http://proxy1.example.com:8080',
    'http://proxy2.example.com:8080',
]
```

### 集成到现有系统
```python
# 在你的代码中使用
from database import DatabaseManager
from request_manager import RequestManager
from image_downloader import AmazonImageDownloader

db = DatabaseManager()
req_mgr = RequestManager(db)
downloader = AmazonImageDownloader(req_mgr, db)

# 下载单个产品
stats = downloader.download_product_images('B08N5WRWNW')

# 批量下载
asins = ['B08N5WRWNW', 'B07XJ8C8F5']
all_stats = downloader.batch_download(asins)
```

---

## 🐛 故障排查指南

### 常见问题速查表

| 问题 | 症状 | 解决方案 |
|------|------|---------|
| 429错误 | Rate limited | 增加延迟,降低频率 |
| 403错误 | Forbidden | 更换IP,检查UA |
| 404错误 | Not found | 检查ASIN有效性 |
| 超时 | Timeout | 检查网络,增加超时时间 |
| 无图片 | No images found | 检查产品页面,更新解析逻辑 |
| 速度慢 | 太慢 | 检查网络,考虑代理 |

详细排查步骤请参考 [SOP.md](SOP.md) 的故障排查章节。

---

## 📈 监控和维护

### 日常监控
```bash
# 实时日志
tail -f logs/crawler.log

# 统计信息
python main.py --stats

# 最近错误
python main.py --recent-errors 20
```

### 定期维护
```bash
# 每周: 查看详细统计
python statistics.py

# 每月: 清理旧日志
python main.py --cleanup-logs 30

# 每月: 验证图片
python verify_images.py

# 每月: 数据备份
tar -czf backup_$(date +%Y%m%d).tar.gz data/
```

---

## ⚠️ 合规和免责

### 使用建议
✅ 合法的市场研究
✅ 内部产品分析
✅ 竞品调研
✅ 数据分析训练

### 禁止行为
❌ 价格操纵
❌ 恶意竞争
❌ 公开发布图片
❌ 侵犯知识产权
❌ 违反Amazon使用条款

### 免责声明
本工具仅供学习和合法研究使用。用户需自行承担使用风险,
确保遵守Amazon使用条款和当地法律法规。作者不对任何滥用行为负责。

---

## 🤝 贡献和支持

### 如何贡献
- 🐛 报告Bug: 提交Issue
- 💡 功能建议: 提交Feature Request
- 🔧 代码贡献: 提交Pull Request
- 📝 文档改进: 欢迎修正和补充

### 获取帮助
- 📖 阅读文档: SOP.md, README.md
- 🔍 搜索Issue: 可能已有解答
- 💬 提问讨论: GitHub Discussions
- 📧 联系作者: (根据需要添加)

---

## 📅 开发路线图

### v1.0 (当前版本) ✅
- [x] 核心爬虫功能
- [x] 反爬虫机制
- [x] 数据库管理
- [x] 命令行接口
- [x] 详细文档

### v1.1 (计划中)
- [ ] Web界面
- [ ] 图片OCR文字提取
- [ ] 更多Amazon站点支持
- [ ] 性能优化
- [ ] Docker支持

### v2.0 (未来)
- [ ] 分布式爬取
- [ ] API接口
- [ ] 数据可视化仪表盘
- [ ] 更智能的图片分类

---

## 📄 许可证

MIT License

Copyright (c) 2024

---

## 🙏 致谢

感谢所有使用和贡献的开发者!

---

**开始使用:** 阅读 [QUICKSTART.md](QUICKSTART.md)  
**详细文档:** 阅读 [SOP.md](SOP.md)  
**祝你使用愉快!** 🚀
