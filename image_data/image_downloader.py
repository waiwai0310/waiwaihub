"""
Image Downloader - 亚马逊图片下载核心逻辑
"""
import re
import time
import logging
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from urllib.parse import urlparse
from bs4 import BeautifulSoup
import config
from request_manager import RequestManager
from database import DatabaseManager

try:
    from playwright.sync_api import sync_playwright  # type: ignore[reportMissingImports]
except ImportError:
    sync_playwright = None


logger = logging.getLogger(__name__)


class AmazonImageDownloader:
    """亚马逊产品图片下载器"""
    
    def __init__(self, request_manager: RequestManager, db_manager: DatabaseManager):
        self.request_manager = request_manager
        self.db_manager = db_manager
        self.image_dir = config.IMAGE_DIR
    
    def _build_product_url(self, asin: str, domain: str = 'us') -> str:
        """构建产品页面URL"""
        base_domain = config.AMAZON_DOMAINS.get(domain, config.AMAZON_DOMAINS['us'])
        return f"https://www.{base_domain}/dp/{asin}"
    
    def _extract_image_urls_from_html(self, html: str, product_url: str) -> List[str]:
        """
        从HTML中提取所有产品图片URL
        
        亚马逊图片通常在以下位置:
        1. #landingImage (主图)
        2. #imageBlock 中的 data-a-dynamic-image
        3. #altImages 中的缩略图
        """
        soup = BeautifulSoup(html, 'html.parser')
        image_urls = []
        
        # 方法1: 提取 data-a-dynamic-image 属性(JSON格式)
        # 这个属性包含多个尺寸的图片URL
        elements = soup.find_all(attrs={'data-a-dynamic-image': True})
        for elem in elements:
            import json
            try:
                image_data = json.loads(elem['data-a-dynamic-image'])
                # image_data 格式: {"url1": [width, height], "url2": [width, height]}
                for url in image_data.keys():
                    if url not in image_urls:
                        image_urls.append(url)
            except:
                pass
        
        # 方法2: 查找 #landingImage
        landing_image = soup.find('img', id='landingImage')
        if landing_image and landing_image.get('src'):
            url = landing_image['src']
            if url.startswith('http') and url not in image_urls:
                image_urls.append(url)
        
        # 方法3: 提取所有包含 'images-na.ssl-images-amazon.com' 或 'm.media-amazon.com' 的图片
        all_imgs = soup.find_all('img', src=True)
        for img in all_imgs:
            src = img['src']
            if ('images-na.ssl-images-amazon.com' in src or 
                'm.media-amazon.com' in src or
                'images-amazon.com' in src):
                if src.startswith('http') and src not in image_urls:
                    # 跳过很小的图片(通常是icon)
                    if '_AC_' in src or '_SL' in src or '_SX' in src or '_SY' in src:
                        image_urls.append(src)
        
        # 方法4: 从脚本中提取(备用)
        scripts = soup.find_all('script', type='text/javascript')
        for script in scripts:
            if script.string:
                # 使用正则提取图片URL
                urls = re.findall(
                    r'https://[^"\']+(?:images-na\.ssl-images-amazon|m\.media-amazon)\.com/images/I/[^"\']+\.(?:jpg|jpeg|png)',
                    script.string
                )
                for url in urls:
                    if url not in image_urls:
                        image_urls.append(url)
        
        logger.info(f"从页面提取到 {len(image_urls)} 个图片链接")
        return image_urls

    def _fetch_rendered_html_with_playwright(self, product_url: str) -> Optional[str]:
        """使用 Playwright 获取 JS 渲染后的完整页面 HTML"""
        if sync_playwright is None:
            logger.warning("未安装 Playwright，回退为 requests HTML")
            return None

        try:
            with sync_playwright() as p:
                # 可视化浏览器 + 持久化 storage_state，便于复用已通过验证的会话
                browser = p.chromium.launch(headless=config.PLAYWRIGHT_HEADLESS)
                storage_state_path = config.PLAYWRIGHT_STORAGE_STATE_FILE

                context_args = {
                    "user_agent": self.request_manager._get_random_user_agent(),
                    "viewport": {"width": 1366, "height": 900},
                }
                if storage_state_path.exists():
                    context_args["storage_state"] = str(storage_state_path)
                    logger.info(f"正在加载 Playwright 会话状态: {storage_state_path}")

                context = browser.new_context(**context_args)
                page = context.new_page()
                page.goto(
                    product_url,
                    timeout=config.PLAYWRIGHT_NAV_TIMEOUT_MS,
                    wait_until='domcontentloaded'
                )
                page.wait_for_timeout(config.PLAYWRIGHT_WAIT_AFTER_GOTO_MS)
                html = page.content()

                # 命中验证码时，给用户留时间在弹出的浏览器里手动通过
                if self._is_captcha_page(html):
                    logger.warning(
                        "检测到 Amazon 验证页面。"
                        f"请在弹出的浏览器中于 {config.PLAYWRIGHT_CAPTCHA_MAX_WAIT_SECONDS}s 内完成验证。"
                    )
                    deadline = time.time() + config.PLAYWRIGHT_CAPTCHA_MAX_WAIT_SECONDS
                    while time.time() < deadline:
                        page.wait_for_timeout(config.PLAYWRIGHT_CAPTCHA_POLL_SECONDS * 1000)
                        html = page.content()
                        if not self._is_captcha_page(html):
                            logger.info("验证已通过，正在保存 Playwright 会话状态。")
                            break

                if not self._is_captcha_page(html):
                    storage_state_path.parent.mkdir(parents=True, exist_ok=True)
                    context.storage_state(path=str(storage_state_path))
                    logger.info(f"已保存 Playwright 会话状态到: {storage_state_path}")

                browser.close()
                return html
        except Exception as e:
            logger.warning(f"Playwright 渲染失败，回退为 requests HTML: {e}")
            return None

    def _extract_hires_image_urls(self, html: str) -> List[str]:
        """提取主图/轮播图 hiRes 高清地址"""
        hires_urls = []
        seen = set()

        # 兼容常见 JSON 片段： "hiRes":"https://..."
        matches = re.findall(r'"hiRes"\s*:\s*"([^"]+)"', html)
        for url in matches:
            normalized = (
                url.replace('\\/', '/')
                .replace('\\u0026', '&')
                .replace('\\u002F', '/')
            )
            if normalized.startswith('https://') and normalized not in seen:
                seen.add(normalized)
                hires_urls.append(normalized)

        return hires_urls

    def _extract_aplus_image_urls(self, html: str, current_asin: str) -> List[str]:
        """提取 A+ 模块图片地址"""
        soup = BeautifulSoup(html, 'html.parser')
        aplus_urls = []
        seen = set()
        # 仅限定在常见 A+ 容器中抓图，避免混入推荐位/广告位图片
        container_selectors = ['#aplus_feature_div', '#aplus', '#aplus3p_feature_div']
        aplus_containers = []
        for selector in container_selectors:
            aplus_containers.extend(soup.select(selector))

        if not aplus_containers:
            aplus_containers = [soup]

        for container in aplus_containers:
            for img in container.find_all('img'):
                src = img.get('src') or img.get('data-src')
                if not src:
                    continue
                if 'aplus-media-library-service-media' not in src:
                    continue

                # 过滤比较表模块中的图片，这些通常包含其他 ASIN 的商品卡片图
                comparison_wrapper = img.find_parent(
                    attrs={
                        'class': lambda c: c and (
                            'comparison-table' in c or
                            'comparison-table-scroller' in c
                        )
                    }
                )
                if comparison_wrapper is not None:
                    continue

                # 如果图片在商品链接里，且链接 ASIN 与当前商品不同，则跳过
                product_anchor = img.find_parent('a', href=True)
                if product_anchor is not None:
                    href = product_anchor.get('href', '')
                    asin_match = re.search(r'/dp/([A-Z0-9]{10})', href, flags=re.IGNORECASE)
                    if asin_match:
                        linked_asin = asin_match.group(1).upper()
                        if linked_asin != current_asin.upper():
                            continue

                normalized = src.strip()
                if normalized.startswith('//'):
                    normalized = f'https:{normalized}'
                if normalized.startswith('https://') and normalized not in seen:
                    seen.add(normalized)
                    aplus_urls.append(normalized)

        return aplus_urls

    def _build_candidate_urls(
        self,
        asin: str,
        html: str,
        product_url: str,
        strict_product_images: bool,
    ) -> List[str]:
        """构建候选图片列表，可切换严格模式。"""
        hires_urls = self._extract_hires_image_urls(html)
        aplus_urls = self._extract_aplus_image_urls(html, current_asin=asin)
        fallback_urls = []
        if not strict_product_images:
            fallback_urls = self._extract_image_urls_from_html(html, product_url)

        image_urls = []
        for url in hires_urls + aplus_urls + fallback_urls:
            if url not in image_urls:
                image_urls.append(url)

        logger.info(
            f"{asin}: Extracted images - hiRes={len(hires_urls)}, "
            f"A+={len(aplus_urls)}, fallback={len(fallback_urls)}, total={len(image_urls)}, "
            f"strict={strict_product_images}"
        )
        return image_urls

    def _is_captcha_page(self, html: str) -> bool:
        """检测是否命中 Amazon 验证页"""
        lower_html = html.lower()
        markers = [
            'captcha',
            'enter the characters you see below',
            '/errors/validatecaptcha',
            'type the characters you see in this image',
        ]
        return any(marker in lower_html for marker in markers)
    
    def _upgrade_image_url(self, url: str) -> str:
        """
        升级图片URL到最高质量
        
        亚马逊图片URL格式:
        https://m.media-amazon.com/images/I/71ABC123._AC_SX679_.jpg
        
        参数说明:
        - _SL1500_: 最长边1500px
        - _AC_SX679_: 宽度679px
        - _AC_SY879_: 高度879px
        """
        # 移除现有的尺寸参数
        url = re.sub(r'\._[A-Z]{2,3}_[A-Z]{2}\d+_', '.', url)
        
        # 添加高质量尺寸参数
        # 在文件扩展名前插入尺寸参数
        for size_param in config.IMAGE_SIZE_PRIORITY:
            test_url = re.sub(r'\.([a-z]+)$', f'{size_param}.\\1', url)
            return test_url
        
        return url
    
    def _get_asin_image_dir(self, asin: str) -> Path:
        """获取ASIN专属的图片目录"""
        asin_dir = self.image_dir / asin
        asin_dir.mkdir(parents=True, exist_ok=True)
        return asin_dir
    
    def _generate_filename(self, asin: str, index: int, url: str) -> str:
        """生成图片文件名"""
        # 提取原始扩展名
        ext = '.jpg'  # 默认
        match = re.search(r'\.([a-z]+)(?:\?|$)', url.lower())
        if match:
            ext = f'.{match.group(1)}'
        
        return config.IMAGE_NAMING_PATTERN.format(asin=asin, index=index) if '{' in config.IMAGE_NAMING_PATTERN else f'{asin}_{index}{ext}'
    
    def download_product_images(
        self, 
        asin: str, 
        domain: str = 'us',
        max_images: int = config.MAX_IMAGES_PER_PRODUCT,
        skip_existing: bool = True,
        strict_product_images: bool = config.STRICT_PRODUCT_IMAGES,
    ) -> Dict:
        """
        下载指定产品的所有图片
        
        Args:
            asin: 产品ASIN
            domain: Amazon域名(us, uk, jp等)
            max_images: 最多下载图片数
            skip_existing: 是否跳过已下载的图片
        
        Returns:
            下载统计信息
        """
        logger.info(f"开始下载 ASIN: {asin}")
        
        stats = {
            'asin': asin,
            'total': 0,
            'success': 0,
            'failed': 0,
            'skipped': 0,
            'downloaded_files': [],
            'errors': []
        }
        
        start_time = time.time()
        
        # 1. 获取产品页面
        product_url = self._build_product_url(asin, domain)
        response = self.request_manager.get(product_url)
        
        if not response:
            error_msg = "获取商品页面失败"
            logger.error(f"{asin}: {error_msg}")
            stats['errors'].append(error_msg)
            return stats
        
        # 添加产品到数据库
        self.db_manager.add_product(asin=asin, url=product_url)
        
        # 2. Playwright 优先获取完整渲染页面，再提取主图/轮播图 + A+ 图
        html = self._fetch_rendered_html_with_playwright(product_url) or response.text

        if self._is_captcha_page(html):
            error_msg = "被 Amazon 验证码/验证页拦截"
            logger.warning(f"{asin}: {error_msg}")
            stats['errors'].append(error_msg)
            return stats

        image_urls = self._build_candidate_urls(
            asin=asin,
            html=html,
            product_url=product_url,
            strict_product_images=strict_product_images,
        )
        
        if not image_urls:
            error_msg = "商品页面未找到图片"
            logger.warning(f"{asin}: {error_msg}")
            stats['errors'].append(error_msg)
            return stats
        
        # 3. 升级URL到高质量并去重
        upgraded_urls = []
        seen = set()
        for url in image_urls[:max_images]:
            upgraded = self._upgrade_image_url(url)
            # 简单去重(基于URL的核心部分)
            url_key = re.sub(r'\._[A-Z_0-9]+\.', '.', upgraded)
            if url_key not in seen:
                seen.add(url_key)
                upgraded_urls.append(upgraded)
        
        logger.info(f"{asin}: 待下载去重后图片数 {len(upgraded_urls)}")
        stats['total'] = len(upgraded_urls)
        
        # 4. 下载图片
        asin_dir = self._get_asin_image_dir(asin)
        
        for idx, image_url in enumerate(upgraded_urls, 1):
            # 检查是否已下载
            if skip_existing and self.db_manager.is_image_downloaded(asin, image_url):
                logger.debug(f"{asin}: 第 {idx} 张图片已下载，跳过")
                stats['skipped'] += 1
                continue
            
            # 生成文件路径
            filename = self._generate_filename(asin, idx, image_url)
            filepath = asin_dir / filename
            
            # 下载
            download_start = time.time()
            success, error = self.request_manager.download_binary(
                url=image_url,
                save_path=str(filepath),
                referer=product_url
            )
            download_time = time.time() - download_start
            
            if success:
                file_size = filepath.stat().st_size
                stats['success'] += 1
                stats['downloaded_files'].append(str(filepath))
                
                # 记录成功
                self.db_manager.record_download(
                    asin=asin,
                    image_url=image_url,
                    status='success',
                    local_path=str(filepath),
                    file_size=file_size,
                    download_time=download_time
                )
                
                logger.info(f"{asin}: 已下载图片 {idx}/{len(upgraded_urls)} ({file_size} 字节)")
            else:
                stats['failed'] += 1
                stats['errors'].append(f"第 {idx} 张图片: {error}")
                
                # 记录失败
                self.db_manager.record_download(
                    asin=asin,
                    image_url=image_url,
                    status='failed',
                    error_message=error,
                    download_time=download_time
                )
                
                logger.error(f"{asin}: 下载第 {idx} 张图片失败: {error}")
        
        total_time = time.time() - start_time
        logger.info(f"{asin}: 完成，耗时 {total_time:.2f}s - 成功: {stats['success']}, 失败: {stats['failed']}, 跳过: {stats['skipped']}")
        
        return stats
    
    def batch_download(
        self, 
        asin_list: List[str], 
        domain: str = 'us',
        max_images_per_product: int = config.MAX_IMAGES_PER_PRODUCT,
        skip_existing: bool = True,
        strict_product_images: bool = config.STRICT_PRODUCT_IMAGES,
    ) -> List[Dict]:
        """
        批量下载多个产品的图片
        
        Args:
            asin_list: ASIN列表
            domain: Amazon域名
            max_images_per_product: 每个产品最多下载图片数
        
        Returns:
            每个产品的下载统计列表
        """
        logger.info(f"开始批量下载，共 {len(asin_list)} 个商品")
        
        all_stats = []
        
        for i, asin in enumerate(asin_list, 1):
            logger.info(f"正在处理商品 {i}/{len(asin_list)}: {asin}")
            
            stats = self.download_product_images(
                asin=asin,
                domain=domain,
                max_images=max_images_per_product,
                skip_existing=skip_existing,
                strict_product_images=strict_product_images,
            )
            
            all_stats.append(stats)
        
        # 汇总统计
        total_stats = {
            'total_products': len(asin_list),
            'total_images': sum(s['total'] for s in all_stats),
            'success': sum(s['success'] for s in all_stats),
            'failed': sum(s['failed'] for s in all_stats),
            'skipped': sum(s['skipped'] for s in all_stats),
        }
        
        logger.info(f"批量下载完成: {total_stats}")
        
        return all_stats
