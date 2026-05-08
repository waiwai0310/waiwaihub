"""
Request Manager - 安全的HTTP请求管理
处理反爬虫、重试、频率控制
"""
import time
import random
import logging
from typing import Optional, Dict
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from collections import deque
from datetime import datetime, timedelta
import config


logger = logging.getLogger(__name__)


class RateLimiter:
    """令牌桶算法实现的速率限制器"""
    
    def __init__(self, calls: int, period: int):
        """
        Args:
            calls: 时间窗口内允许的调用次数
            period: 时间窗口大小(秒)
        """
        self.calls = calls
        self.period = period
        self.timestamps = deque(maxlen=calls)
    
    def wait_if_needed(self):
        """如果超过速率限制,则等待"""
        now = datetime.now()
        
        # 清理过期的时间戳
        cutoff = now - timedelta(seconds=self.period)
        while self.timestamps and self.timestamps[0] < cutoff:
            self.timestamps.popleft()
        
        # 检查是否需要等待
        if len(self.timestamps) >= self.calls:
            sleep_time = (self.timestamps[0] - cutoff).total_seconds()
            if sleep_time > 0:
                logger.info(f"触发速率限制，等待 {sleep_time:.2f}s")
                time.sleep(sleep_time)
        
        # 记录本次请求
        self.timestamps.append(now)


class RequestManager:
    """管理HTTP请求,实现反爬虫策略"""
    
    def __init__(self, db_manager=None):
        self.db_manager = db_manager
        self.session = self._create_session()
        self.rate_limiter = RateLimiter(
            calls=config.RATE_LIMIT_CALLS,
            period=config.RATE_LIMIT_PERIOD
        ) if config.RATE_LIMIT_ENABLED else None
        self.proxy_index = 0
        
        logger.info("请求管理器已初始化")
    
    def _create_session(self) -> requests.Session:
        """创建配置好的 requests.Session"""
        session = requests.Session()
        
        # 配置重试策略
        retry_strategy = Retry(
            total=config.MAX_RETRIES,
            backoff_factor=config.RETRY_BACKOFF,
            status_forcelist=config.RETRY_STATUS_CODES,
            allowed_methods=["GET", "HEAD"],
        )
        
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        
        return session
    
    def _get_random_user_agent(self) -> str:
        """随机选择一个 User-Agent"""
        return random.choice(config.USER_AGENTS)
    
    def _get_headers(self, referer: str = None) -> Dict:
        """构建请求头"""
        headers = {
            'User-Agent': self._get_random_user_agent(),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Cache-Control': 'max-age=0',
        }
        
        if referer:
            headers['Referer'] = referer
        
        return headers
    
    def _get_proxy(self) -> Optional[Dict]:
        """获取代理(轮询)"""
        if not config.USE_PROXY or not config.PROXY_LIST:
            return None
        
        proxy = config.PROXY_LIST[self.proxy_index % len(config.PROXY_LIST)]
        self.proxy_index += 1
        
        return {
            'http': proxy,
            'https': proxy,
        }
    
    def _random_delay(self):
        """随机延迟,模拟人类行为"""
        delay = random.uniform(config.REQUEST_DELAY_MIN, config.REQUEST_DELAY_MAX)
        logger.debug(f"随机等待 {delay:.2f}s")
        time.sleep(delay)
    
    def get(
        self, 
        url: str, 
        referer: str = None,
        stream: bool = False,
        timeout: int = config.REQUEST_TIMEOUT
    ) -> Optional[requests.Response]:
        """
        安全的 GET 请求
        
        Args:
            url: 请求URL
            referer: Referer头
            stream: 是否流式传输(下载大文件时使用)
            timeout: 超时时间
        
        Returns:
            Response对象,失败返回None
        """
        # 速率限制
        if self.rate_limiter:
            self.rate_limiter.wait_if_needed()
        
        # 随机延迟
        self._random_delay()
        
        start_time = time.time()
        response = None
        error_type = None
        
        try:
            headers = self._get_headers(referer)
            proxies = self._get_proxy()
            
            logger.debug(f"发起 GET 请求: {url}")
            
            response = self.session.get(
                url,
                headers=headers,
                proxies=proxies,
                timeout=timeout,
                stream=stream,
                allow_redirects=True
            )
            
            response_time = time.time() - start_time
            
            # 记录请求日志
            if self.db_manager:
                self.db_manager.log_request(
                    url=url,
                    status_code=response.status_code,
                    response_time=response_time
                )
            
            # 检查状态码
            if response.status_code == 200:
                logger.debug(f"请求成功: {url} ({response_time:.2f}s)")
                return response
            
            elif response.status_code == 429:
                error_type = 'rate_limited'
                logger.warning(f"被限流: {url}")
                # 额外延迟
                time.sleep(60)
                
            elif response.status_code in config.FATAL_STATUS_CODES:
                error_type = 'fatal_error'
                logger.error(f"致命错误 {response.status_code}: {url}")
                
            else:
                error_type = 'http_error'
                logger.warning(f"HTTP 错误 {response.status_code}: {url}")
            
            response.raise_for_status()
            
        except requests.exceptions.Timeout:
            error_type = 'timeout'
            logger.error(f"请求超时: {url}")
            
        except requests.exceptions.ProxyError:
            error_type = 'proxy_error'
            logger.error(f"代理错误: {url}")
            
        except requests.exceptions.ConnectionError:
            error_type = 'connection_error'
            logger.error(f"连接错误: {url}")
            
        except requests.exceptions.RequestException as e:
            error_type = 'request_error'
            logger.error(f"请求异常: {url} - {e}")
        
        # 记录错误
        if self.db_manager and error_type:
            response_time = time.time() - start_time
            self.db_manager.log_request(
                url=url,
                status_code=response.status_code if response else None,
                response_time=response_time,
                error_type=error_type
            )
        
        return None
    
    def download_binary(
        self, 
        url: str, 
        save_path: str,
        referer: str = None
    ) -> tuple[bool, Optional[str]]:
        """
        下载二进制文件(如图片)
        
        Args:
            url: 文件URL
            save_path: 保存路径
            referer: Referer头
        
        Returns:
            (成功标志, 错误信息)
        """
        try:
            response = self.get(url, referer=referer, stream=True)
            
            if not response:
                return False, "Failed to get response"
            
            # 检查 Content-Type
            content_type = response.headers.get('Content-Type', '')
            if not content_type.startswith('image/'):
                logger.warning(f"非预期内容类型: {content_type}，URL: {url}")
            
            # 流式下载
            with open(save_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            
            logger.debug(f"下载完成: {save_path}")
            return True, None
            
        except Exception as e:
            error_msg = f"下载失败: {e}"
            logger.error(error_msg)
            return False, error_msg
    
    def close(self):
        """关闭session"""
        self.session.close()
        logger.info("请求管理器已关闭")
