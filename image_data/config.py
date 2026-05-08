"""
Amazon Image Crawler - Configuration
安全稳定的配置管理
"""
import os
from pathlib import Path

# ==================== 基础配置 ====================
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
LOG_DIR = BASE_DIR / "logs"
IMAGE_DIR = DATA_DIR / "images"

# 创建必要目录
for dir_path in [DATA_DIR, LOG_DIR, IMAGE_DIR]:
    dir_path.mkdir(parents=True, exist_ok=True)

# ==================== 爬虫安全配置 ====================
# User-Agent 池(模拟真实浏览器)
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
]

# ==================== 请求控制 ====================
# 请求间隔(秒)- 关键安全参数
REQUEST_DELAY_MIN = 2.0  # 最小延迟
REQUEST_DELAY_MAX = 5.0  # 最大延迟
REQUEST_TIMEOUT = 30     # 请求超时

# 重试策略
MAX_RETRIES = 3          # 最大重试次数
RETRY_BACKOFF = 2        # 重试退避倍数(指数退避)

# 并发控制
MAX_CONCURRENT_REQUESTS = 2  # 最大并发数(保守设置)

# ==================== 代理配置 ====================
USE_PROXY = False  # 是否使用代理
PROXY_LIST = [
    # 'http://proxy1.example.com:8080',
    # 'http://proxy2.example.com:8080',
]

# ==================== 图片处理配置 ====================
# 支持的图片格式
SUPPORTED_IMAGE_FORMATS = ['.jpg', '.jpeg', '.png', '.webp']

# 图片尺寸优先级(Amazon 图片 URL 参数)
# 格式: ._SL1500_ (1500px), ._AC_SX679_ (679px宽)
IMAGE_SIZE_PRIORITY = [
    '_SL1500_',  # 1500px 大图
    '_AC_SL1500_',
    '_SL1000_',  # 1000px
    '_AC_SX679_',  # 679px 宽
]

# 图片存储策略
IMAGE_NAMING_PATTERN = '{asin}_{index}.jpg'  # 命名模式
MAX_IMAGES_PER_PRODUCT = 30 # 每个产品最多下载图片数
STRICT_PRODUCT_IMAGES = True  # 严格模式: 仅主图/轮播图 + A+容器图

# ==================== 数据库配置 ====================
# SQLite 数据库路径(记录下载历史,去重)
DB_PATH = DATA_DIR / "crawler_db.sqlite"

# ==================== 日志配置 ====================
LOG_LEVEL = "INFO"
LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
LOG_FILE = LOG_DIR / "crawler.log"
LOG_MAX_BYTES = 10 * 1024 * 1024  # 10MB
LOG_BACKUP_COUNT = 5

# ==================== Amazon 域名配置 ====================
AMAZON_DOMAINS = {
    'us': 'amazon.com',
    'uk': 'amazon.co.uk',
    'jp': 'amazon.co.jp',
    'de': 'amazon.de',
    'fr': 'amazon.fr',
}
DEFAULT_DOMAIN = 'us'

# ==================== 错误处理 ====================
# HTTP 状态码处理策略
RETRY_STATUS_CODES = [429, 500, 502, 503, 504]  # 可重试的状态码
FATAL_STATUS_CODES = [403, 404]  # 致命错误,不重试

# ==================== 合规性配置 ====================
RESPECT_ROBOTS_TXT = True  # 遵守 robots.txt
RATE_LIMIT_ENABLED = True  # 启用速率限制
RATE_LIMIT_CALLS = 30      # 每分钟最多请求数
RATE_LIMIT_PERIOD = 60     # 时间窗口(秒)

# ==================== 监控和报警 ====================
ENABLE_METRICS = True  # 启用指标收集
METRICS_FILE = DATA_DIR / "metrics.json"

# ==================== Playwright 会话复用 ====================
PLAYWRIGHT_STORAGE_STATE_FILE = DATA_DIR / "playwright_storage_state.json"
PLAYWRIGHT_HEADLESS = False
PLAYWRIGHT_NAV_TIMEOUT_MS = 60000
PLAYWRIGHT_WAIT_AFTER_GOTO_MS = 3000
PLAYWRIGHT_CAPTCHA_MAX_WAIT_SECONDS = 180
PLAYWRIGHT_CAPTCHA_POLL_SECONDS = 5

# ==================== Selenium 会话复用（卖家精灵登录态） ====================
# 使用本机 Chrome 用户目录复用登录态（含卖家精灵扩展登录）
SELENIUM_USE_LOCAL_CHROME_PROFILE = True
SELENIUM_CHROME_USER_DATA_DIR = os.getenv("LOCALAPPDATA", "") + r"\Google\Chrome\User Data"
SELENIUM_CHROME_PROFILE_DIR = "Default"
SELENIUM_WAIT_AFTER_GOTO_SECONDS = 8
# 如果首次需要手动登录，可设置 >0（秒），爬虫会在打开页面后等待
SELENIUM_MANUAL_LOGIN_WAIT_SECONDS = 60

# 报警阈值
ALERT_ERROR_RATE = 0.3  # 错误率超过30%报警
ALERT_BLOCK_RATE = 0.1  # 被封禁率超过10%报警
