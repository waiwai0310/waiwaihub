# Amazon Image Crawler

> 安全优先的亚马逊图片抓取工具，支持 CLI 和异步 API 两种调用方式。

## 核心能力

- 支持抓取主图/轮播图（`hiRes`）和 A+ 图片（DOM `img`）
- Playwright 渲染动态页面，兼容 Amazon 前端数据延迟注入
- 自动检测验证码页，并支持人工通过后复用会话状态
- SQLite 记录下载历史，支持去重和统计
- 提供 FastAPI 异步任务接口：提交任务 + 查询进度

## 快速开始

```bash
pip install -r requirements.txt
python -m playwright install chromium
```

最低业务输入只需要 ASIN（直接传列表或文件）。

## CLI 模式

```bash
# 单个 ASIN
python main.py -a B08N5WRWNW

# 多个 ASIN
python main.py -a B08N5WRWNW B0FVFGV3B7

# 从文件读取
python main.py -f asin_list_example.txt

# 指定站点和每商品最大图片数
python main.py -a B08N5WRWNW -d us -m 5

# 强制重下（忽略历史下载记录）
python main.py -a B08N5WRWNW --force-redownload

# 非严格模式（允许全页兜底抓图，可能混入其他商品图片）
python main.py -a B08N5WRWNW --allow-fallback-images
```

### CLI 参数说明（当前默认值）

- `-a/--asin`: ASIN 列表
- `-f/--file`: ASIN 文件（每行一个）
- `-d/--domain`: 站点，默认 `us`
- `-m/--max-images`: 每商品最多下载数，默认 `9`
- `--skip-existing`: 跳过已下载（默认关闭）
- `--force-redownload`: 强制重下（优先级高于 `--skip-existing`）
- `--allow-fallback-images`: 关闭严格模式，允许全页兜底抓图

## API 模式

启动服务：

```bash
uvicorn api_server:app --host 0.0.0.0 --port 8000 --reload
```

接口文档：

- Swagger UI: `http://127.0.0.1:8000/docs`
- ReDoc: `http://127.0.0.1:8000/redoc`

健康检查：

```bash
curl http://127.0.0.1:8000/health
```

提交任务（传 ASIN 列表）：

```bash
curl -X POST "http://127.0.0.1:8000/api/crawl/start" ^
  -H "Content-Type: application/json" ^
  -d "{\"asins\":[\"B08N5WRWNW\"],\"domain\":\"us\",\"max_images\":5}"
```

或按文件提交：

```bash
curl -X POST "http://127.0.0.1:8000/api/crawl/start" ^
  -H "Content-Type: application/json" ^
  -d "{\"asin_file\":\"asin_list_example.txt\",\"domain\":\"us\"}"
```

查询任务状态：

```bash
curl "http://127.0.0.1:8000/api/jobs/<job_id>"
```

## 常见问题

### 为什么显示 `Skipped: N`？

这些图片在数据库中已有成功记录。你可以：

- 直接强制重下：`python main.py -a <ASIN> --force-redownload`
- 或按需开启跳过：`--skip-existing`

### 为什么 A+ 没下载到？

常见原因：

- 当前商品页面没有 A+ 模块
- 命中验证码/风控页导致页面结构不完整
- `max_images` 太小，被主图先占满

建议先提高 `-m`（如 `-m 30`），并检查日志中是否有 `A+=...`。

## 验证页与会话复用说明

- 当 Amazon 返回验证码页时，程序会提示 `Blocked by Amazon captcha/verification page`
- Playwright 会在可视化浏览器中等待你手动完成验证
- 验证通过后保存 `storage_state`，后续任务自动复用
- 相关配置位于 `config.py` 中 `PLAYWRIGHT_*` 参数

## 缓存清理

Linux/macOS:

```bash
rm -f data/playwright_storage_state.json
rm -f data/crawler_db.sqlite
rm -rf data/images
```

Windows PowerShell:

```powershell
Remove-Item "data\playwright_storage_state.json" -Force -ErrorAction SilentlyContinue
Remove-Item "data\crawler_db.sqlite" -Force -ErrorAction SilentlyContinue
Remove-Item "data\images" -Recurse -Force -ErrorAction SilentlyContinue
```

## 目录结构

```text
image_data/
├── main.py                    # CLI 入口
├── api_server.py              # FastAPI 入口
├── image_downloader.py        # 抓取与下载核心
├── request_manager.py         # HTTP 请求管理
├── database.py                # SQLite 管理
├── config.py                  # 全局配置
├── app/
│   ├── schemas.py             # API 数据模型
│   ├── job_store.py           # 任务状态存储
│   ├── routers/crawl.py       # API 路由
│   └── services/crawler.py    # 后台任务服务
├── data/
│   ├── images/
│   └── crawler_db.sqlite
└── logs/crawler.log
```

## 常用管理命令（CLI）

```bash
python main.py --stats
python main.py --recent-errors 20
python main.py --cleanup-logs 30
```

## 安全建议

- 不要激进调低 `REQUEST_DELAY_MIN/REQUEST_DELAY_MAX`
- 首次先小批量测试（10 个 ASIN）
- 高并发会显著提高触发风控概率
- 合法合规使用，遵守目标站点条款

## 免责声明

- 本工具仅用于学习和合法业务研究
- 使用风险由使用者自行承担
