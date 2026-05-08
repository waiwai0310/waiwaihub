"""
Product Data Crawler - Amazon产品数据爬取器
用于提取产品的详细信息并输出到Excel
"""
import re
import json
import time
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
from bs4 import BeautifulSoup
from urllib.parse import urlparse
import config
from request_manager import RequestManager
from database import DatabaseManager

# 可选：使用 Selenium 获取完整渲染后的 HTML
try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from webdriver_manager.chrome import ChromeDriverManager
except ImportError:
    webdriver = None
    Options = None
    ChromeDriverManager = None

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None

logger = logging.getLogger(__name__)


class ProductDataCrawler:
    """Amazon产品数据爬取器"""
    
    def __init__(self, request_manager: RequestManager, db_manager: DatabaseManager):
        self.request_manager = request_manager
        self.db_manager = db_manager
    
    def _build_product_url(self, asin: str, domain: str = 'us') -> str:
        """构建产品页面URL"""
        base_domain = config.AMAZON_DOMAINS.get(domain, config.AMAZON_DOMAINS['us'])
        return f"https://www.{base_domain}/dp/{asin}"
    
    def _fetch_rendered_html_with_playwright(self, product_url: str) -> Optional[str]:
        """使用Playwright获取渲染后的HTML"""
        if sync_playwright is None:
            logger.warning("未安装 Playwright，回退为 requests HTML")
            return None

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=config.PLAYWRIGHT_HEADLESS)
                storage_state_path = config.PLAYWRIGHT_STORAGE_STATE_FILE

                context_args = {
                    "user_agent": self.request_manager._get_random_user_agent(),
                    "viewport": {"width": 1366, "height": 900},
                }
                if storage_state_path.exists():
                    context_args["storage_state"] = str(storage_state_path)

                context = browser.new_context(**context_args)
                page = context.new_page()
                page.goto(
                    product_url,
                    timeout=config.PLAYWRIGHT_NAV_TIMEOUT_MS,
                    wait_until='domcontentloaded'
                )
                page.wait_for_timeout(config.PLAYWRIGHT_WAIT_AFTER_GOTO_MS)
                html = page.content()

                # 处理验证码
                if self._is_captcha_page(html):
                    logger.warning(f"检测到验证页面，请在浏览器中完成验证")
                    deadline = time.time() + config.PLAYWRIGHT_CAPTCHA_MAX_WAIT_SECONDS
                    while time.time() < deadline:
                        page.wait_for_timeout(config.PLAYWRIGHT_CAPTCHA_POLL_SECONDS * 1000)
                        html = page.content()
                        if not self._is_captcha_page(html):
                            logger.info("验证已通过")
                            break

                if not self._is_captcha_page(html):
                    storage_state_path.parent.mkdir(parents=True, exist_ok=True)
                    context.storage_state(path=str(storage_state_path))

                browser.close()
                return html
        except Exception as e:
            logger.warning(f"Playwright 渲染失败: {e}")
            return None
    
    def _fetch_rendered_html_with_selenium(self, product_url: str) -> Optional[str]:
        """
        使用 Selenium 获取渲染后的HTML
        
        参考用户提供的示例，尽量贴近真实浏览器行为，减轻风控：
        - 使用 ChromeDriverManager 管理驱动
        - 添加反自动化相关参数
        - 不强制无头模式，方便遇到验证码时手动处理
        """
        if webdriver is None or Options is None or ChromeDriverManager is None:
            logger.warning("未安装 Selenium 或 webdriver-manager，跳过 Selenium 渲染")
            return None

        from selenium.webdriver.chrome.service import Service  # 局部导入，避免未安装时报错

        driver = None
        try:
            chrome_options = Options()
            chrome_options.add_argument("--start-maximized")

            # 反爬关键配置（参考用户示例）
            chrome_options.add_argument("--disable-blink-features=AutomationControlled")
            chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
            chrome_options.add_experimental_option("useAutomationExtension", False)

            # 使用我们自己的 UA，进一步伪装
            chrome_options.add_argument(
                f"user-agent={self.request_manager._get_random_user_agent()}"
            )

            # 复用本机 Chrome 登录态（卖家精灵登录后可直接生效）
            if config.SELENIUM_USE_LOCAL_CHROME_PROFILE and config.SELENIUM_CHROME_USER_DATA_DIR:
                chrome_options.add_argument(f"--user-data-dir={config.SELENIUM_CHROME_USER_DATA_DIR}")
                chrome_options.add_argument(f"--profile-directory={config.SELENIUM_CHROME_PROFILE_DIR}")

            # 优先使用 webdriver-manager，失败则退回系统自带驱动/selenium manager
            try:
                service = Service(ChromeDriverManager().install())
                driver = webdriver.Chrome(service=service, options=chrome_options)
            except Exception as driver_error:
                logger.warning(f"webdriver-manager 初始化失败，尝试本机驱动: {driver_error}")
                driver = webdriver.Chrome(options=chrome_options)

            logger.info(f"使用 Selenium 打开页面: {product_url}")
            driver.get(product_url)

            # 首次需要登录卖家精灵时，留出手动操作时间
            if config.SELENIUM_MANUAL_LOGIN_WAIT_SECONDS > 0:
                logger.info(
                    f"请在浏览器中完成登录，等待 {config.SELENIUM_MANUAL_LOGIN_WAIT_SECONDS}s ..."
                )
                time.sleep(config.SELENIUM_MANUAL_LOGIN_WAIT_SECONDS)

            # 等页面加载完成（包括扩展注入区块）
            time.sleep(config.SELENIUM_WAIT_AFTER_GOTO_SECONDS)

            html = driver.page_source
            return html
        except Exception as e:
            logger.warning(f"Selenium 渲染失败: {e}")
            return None
        finally:
            try:
                if driver is not None:
                    driver.quit()
            except Exception:
                pass
    
    def _is_captcha_page(self, html: str) -> bool:
        """检测是否为验证码页面"""
        captcha_indicators = [
            'Type the characters you see in this image',
            'Enter the characters you see below',
            'Sorry, we just need to make sure you\'re not a robot',
            'api-services-support@amazon.com',
        ]
        return any(indicator.lower() in html.lower() for indicator in captcha_indicators)
    
    def extract_main_image(self, soup: BeautifulSoup) -> Optional[str]:
        """提取首图URL"""
        try:
            # 方法1: landingImage
            landing_img = soup.find('img', id='landingImage')
            if landing_img and landing_img.get('src'):
                return landing_img['src']
            
            # 方法2: data-a-dynamic-image
            elements = soup.find_all(attrs={'data-a-dynamic-image': True})
            for elem in elements:
                try:
                    image_data = json.loads(elem['data-a-dynamic-image'])
                    urls = list(image_data.keys())
                    if urls:
                        return urls[0]
                except:
                    pass
            
            # 方法3: imgTagWrapper中的img
            img_wrapper = soup.find('div', id='imgTagWrapperId')
            if img_wrapper:
                img = img_wrapper.find('img')
                if img and img.get('src'):
                    return img['src']
            
            return None
        except Exception as e:
            logger.error(f"提取首图失败: {e}")
            return None
    
    def extract_brand(self, soup: BeautifulSoup) -> Optional[str]:
        """提取品牌"""
        try:
            # 方法1: bylineInfo
            brand_elem = soup.find('a', id='bylineInfo')
            if brand_elem:
                brand_text = brand_elem.get_text(strip=True)
                # 去掉 "Visit the ... Store" 或 "Brand: "
                brand = re.sub(r'^(Visit the |Brand: |品牌：)', '', brand_text, flags=re.IGNORECASE)
                brand = re.sub(r' Store$', '', brand, flags=re.IGNORECASE)
                return brand.strip()
            
            # 方法2: 通过data-attribute-name="Brand"
            brand_row = soup.find('th', string=re.compile(r'Brand', re.IGNORECASE))
            if brand_row:
                brand_cell = brand_row.find_next_sibling('td')
                if brand_cell:
                    return brand_cell.get_text(strip=True)
            
            # 方法3: 产品信息表格
            for row in soup.find_all('tr'):
                header = row.find('th')
                if header and 'brand' in header.get_text().lower():
                    value = row.find('td')
                    if value:
                        return value.get_text(strip=True)
            
            return None
        except Exception as e:
            logger.error(f"提取品牌失败: {e}")
            return None
    
    def extract_title(self, soup: BeautifulSoup) -> Optional[str]:
        """提取标题"""
        try:
            title_elem = soup.find('span', id='productTitle')
            if title_elem:
                return title_elem.get_text(strip=True)
            
            # 备用方法
            title_elem = soup.find('h1', class_='product-title')
            if title_elem:
                return title_elem.get_text(strip=True)
            
            return None
        except Exception as e:
            logger.error(f"提取标题失败: {e}")
            return None
    
    def extract_price(self, soup: BeautifulSoup) -> Optional[str]:
        """提取价格"""
        try:
            # 方法1: 新版 corePriceDisplay 容器中的实际支付价格（推荐）
            core_price_div = soup.find('div', id='corePriceDisplay_desktop_feature_div')
            if core_price_div:
                # 1）优先用新版的无障碍文本 apex-pricetopay-accessibility-label
                apex_label = core_price_div.find('span', id=re.compile(r'apex-pricetopay-accessibility-label'))
                if apex_label:
                    label_text = apex_label.get_text(strip=True)
                    # 例子："89.99美元，含25%折扣" -> 提取前面的金额部分
                    m = re.search(r'([\d\.,]+)', label_text)
                    if m:
                        # 保留原始整段文本更安全（含货币符号），但如果只有数字就直接返回匹配值
                        amount = m.group(1)
                        # 如果原文本里已经包含货币符号，就直接返回原文本；否则返回数字
                        if any(sym in label_text for sym in ['$', '€', '£', '￥', '元']):
                            return label_text
                        return amount

                # 2）再尝试 priceToPay 里的 a-offscreen（部分站点这里有完整金额）
                offscreen_span = core_price_div.find('span', class_=re.compile(r'a-offscreen'))
                if offscreen_span and offscreen_span.get_text(strip=True):
                    return offscreen_span.get_text(strip=True)

                # 退化为 whole + fraction 形式
                price_whole_span = core_price_div.find('span', class_='a-price-whole')
                if price_whole_span:
                    price_whole = price_whole_span.get_text(strip=True)
                    price_fraction_span = core_price_div.find('span', class_='a-price-fraction')
                    if price_fraction_span:
                        return f"{price_whole}{price_fraction_span.get_text(strip=True)}"
                    return price_whole

            # 方法2: 旧版/兼容写法 - priceblock_dealprice（活动价优先）
            price_elem = soup.find('span', id='priceblock_dealprice')
            if price_elem and price_elem.get_text(strip=True):
                return price_elem.get_text(strip=True)
            
            # 方法3: 旧版/兼容写法 - priceblock_ourprice
            price_elem = soup.find('span', id='priceblock_ourprice')
            if price_elem and price_elem.get_text(strip=True):
                return price_elem.get_text(strip=True)
            
            # 方法4: data-a-color="price"
            price_elem = soup.find('span', attrs={'data-a-color': 'price'})
            if price_elem and price_elem.get_text(strip=True):
                return price_elem.get_text(strip=True)
            
            return None
        except Exception as e:
            logger.error(f"提取价格失败: {e}")
            return None
    
    def extract_promo_price(self, soup: BeautifulSoup) -> Optional[str]:
        """提取活动优惠价"""
        try:
            # 方法1: 新版 corePriceDisplay 中的促销价（如果存在原价+促销价结构）
            core_price_div = soup.find('div', id='corePriceDisplay_desktop_feature_div')
            if core_price_div:
                # 促销价通常是未删除线的 a-price，原价有删除线 a-text-price
                promo_price_span = core_price_div.find(
                    'span',
                    class_=re.compile(r'a-price(?!.*a-text-price)')
                )
                if promo_price_span:
                    offscreen_span = promo_price_span.find('span', class_=re.compile(r'a-offscreen'))
                    if offscreen_span and offscreen_span.get_text(strip=True):
                        return offscreen_span.get_text(strip=True)

            # 方法2: priceblock_dealprice（旧版）
            promo_elem = soup.find('span', id='priceblock_dealprice')
            if promo_elem and promo_elem.get_text(strip=True):
                return promo_elem.get_text(strip=True)
            
            # 方法3: savingPriceOverride
            promo_elem = soup.find('span', id='savingPriceOverride')
            if promo_elem and promo_elem.get_text(strip=True):
                return promo_elem.get_text(strip=True)
            
            # 方法4: 寻找带有 deal/discount/sale 关键字的价格
            deal_price = soup.find('span', class_=re.compile(r'deal|discount|sale', re.IGNORECASE))
            if deal_price and deal_price.get_text(strip=True):
                return deal_price.get_text(strip=True)
            
            return None
        except Exception as e:
            logger.error(f"提取优惠价失败: {e}")
            return None
    
    def extract_rating(self, soup: BeautifulSoup) -> Optional[float]:
        """提取评分"""
        try:
            # 方法1: acrPopover
            rating_elem = soup.find('span', class_='a-icon-alt')
            if rating_elem:
                rating_text = rating_elem.get_text(strip=True)
                match = re.search(r'([\d.]+)\s*out of', rating_text, re.IGNORECASE)
                if match:
                    return float(match.group(1))
            
            # 方法2: data-hook="rating-out-of-text"
            rating_elem = soup.find('span', attrs={'data-hook': 'rating-out-of-text'})
            if rating_elem:
                rating_text = rating_elem.get_text(strip=True)
                match = re.search(r'([\d.]+)', rating_text)
                if match:
                    return float(match.group(1))
            
            return None
        except Exception as e:
            logger.error(f"提取评分失败: {e}")
            return None
    
    def extract_review_count(self, soup: BeautifulSoup) -> Optional[int]:
        """提取评论数量"""
        try:
            # 方法1: acrCustomerReviewText
            review_elem = soup.find('span', id='acrCustomerReviewText')
            if review_elem:
                review_text = review_elem.get_text(strip=True)
                # 提取数字 "1,234 ratings" -> 1234
                match = re.search(r'([\d,]+)', review_text)
                if match:
                    return int(match.group(1).replace(',', ''))
            
            # 方法2: data-hook="total-review-count"
            review_elem = soup.find('span', attrs={'data-hook': 'total-review-count'})
            if review_elem:
                review_text = review_elem.get_text(strip=True)
                match = re.search(r'([\d,]+)', review_text)
                if match:
                    return int(match.group(1).replace(',', ''))
            
            return None
        except Exception as e:
            logger.error(f"提取评论数量失败: {e}")
            return None
    
    def extract_bsr_ranking(self, soup: BeautifulSoup) -> Optional[str]:
        """提取BSR排名（Best Sellers Rank）"""
        try:
            # 方法0：卖家精灵扩展浮层（中文）结构：p.bsr-list-item > span.rank-box
            bsr_item = soup.select_one('p.bsr-list-item span.rank-box')
            if bsr_item:
                m = re.search(r'#\s*([\d,]+)', bsr_item.get_text(" ", strip=True))
                if m:
                    return m.group(1)

            # 查找包含 "Best Sellers Rank" 或中文 "亚马逊热销商品排名" 的元素
            bsr_section = soup.find(
                'th',
                string=re.compile(r'Best Sellers Rank|bestsellers rank|亚马逊热销商品排名', re.IGNORECASE)
            )
            if bsr_section:
                bsr_cell = bsr_section.find_next_sibling('td')
                if bsr_cell:
                    bsr_text = bsr_cell.get_text(strip=True)
                    # 提取第一个排名 "#123 in Category"
                    match = re.search(r'#([\d,]+)', bsr_text)
                    if match:
                        return match.group(1)
            
            # 备用方法：在产品详情中查找
            for li in soup.find_all('li'):
                li_text = li.get_text()
                if 'Best Sellers Rank' in li_text or 'bestsellers rank' in li_text.lower() or '热销商品排名' in li_text:
                    match = re.search(r'#([\d,]+)', li_text)
                    if match:
                        return match.group(1)
            
            return None
        except Exception as e:
            logger.error(f"提取BSR排名失败: {e}")
            return None
    
    def extract_category_rankings(self, soup: BeautifulSoup) -> Dict[str, str]:
        """提取类目排名（大类和小类）"""
        try:
            rankings = {
                'main_category': None,
                'main_category_rank': None,
                'sub_category': None,
                'sub_category_rank': None
            }

            # 方法0：先解析卖家精灵扩展浮层（你贴的 HTML 就是这个结构）
            # 形态示例：#10,070 在 家居与厨房；#1 在 沙发与沙发
            panel_items = soup.select('p.bsr-list-item')
            parsed_ranks = []
            for item in panel_items:
                rank_box = item.select_one('span.rank-box')
                category_span = item.select_one('span.exts-color-blue')
                if rank_box and category_span:
                    rank_match = re.search(r'#\s*([\d,]+)', rank_box.get_text(" ", strip=True))
                    category_text = category_span.get_text(" ", strip=True)
                    if rank_match and category_text:
                        parsed_ranks.append((rank_match.group(1), category_text))

            # 优先识别中英文表头："Best Sellers Rank" / "亚马逊热销商品排名"
            bsr_header = soup.find(
                'th',
                string=re.compile(r'Best Sellers Rank|亚马逊热销商品排名', re.IGNORECASE)
            )

            if not parsed_ranks and bsr_header:
                bsr_cell = bsr_header.find_next_sibling('td')
                if bsr_cell:
                    for li in bsr_cell.find_all('li'):
                        text = li.get_text(" ", strip=True)
                        m = re.search(r'#\s*([\d,]+)\s+(?:in|在)\s+([^(<]+)', text)
                        if m:
                            rank = m.group(1)
                            category = m.group(2).strip()
                            category = re.sub(r'\s*\(.*$', '', category)
                            parsed_ranks.append((rank, category))

            # 如果表头块没解析到，再全局扫 li：
            # 任何 li 文本形如 "#10,070 in Home & Kitchen (...)"、"#1 in Sofas & Couches" 都视为类目排名
            if not parsed_ranks:
                for li in soup.find_all('li'):
                    text = li.get_text(" ", strip=True)
                    if '#' not in text:
                        continue

                    m = re.search(r'#\s*([\d,]+)\s+(?:in|在)\s+([^(<]+)', text)
                    if m:
                        rank = m.group(1)
                        category = m.group(2).strip()
                        # 去掉括号内说明，如 "(See Top 100 in Home & Kitchen)"
                        category = re.sub(r'\s*\(.*$', '', category)
                        parsed_ranks.append((rank, category))

            if parsed_ranks:
                # 第一条当大类
                rankings['main_category_rank'] = parsed_ranks[0][0]
                rankings['main_category'] = parsed_ranks[0][1]
                # 第二条当小类（如果有）
                if len(parsed_ranks) > 1:
                    rankings['sub_category_rank'] = parsed_ranks[1][0]
                    rankings['sub_category'] = parsed_ranks[1][1]
            
            # 无论是否成功解析，都打印最终结果，方便对照 Excel
            logger.info(
                f"[BSR RESULT] main_category={rankings['main_category']}, "
                f"main_category_rank={rankings['main_category_rank']}, "
                f"sub_category={rankings['sub_category']}, "
                f"sub_category_rank={rankings['sub_category_rank']}"
            )
            
            return rankings
        except Exception as e:
            logger.error(f"提取类目排名失败: {e}")
            return {
                'main_category': None,
                'main_category_rank': None,
                'sub_category': None,
                'sub_category_rank': None
            }
    
    def extract_launch_date(self, soup: BeautifulSoup) -> Optional[str]:
        """提取上架时间"""
        try:
            # 查找 "Date First Available"
            date_row = soup.find('th', string=re.compile(r'Date First Available', re.IGNORECASE))
            if date_row:
                date_cell = date_row.find_next_sibling('td')
                if date_cell:
                    return date_cell.get_text(strip=True)
            
            # 备用方法：在产品详情列表中查找
            for row in soup.find_all('tr'):
                header = row.find('th')
                if header and 'date first available' in header.get_text().lower():
                    value = row.find('td')
                    if value:
                        return value.get_text(strip=True)

            # 中文扩展浮层：上架时间：2024-09-22（571天）
            launch_label = soup.find('span', string=re.compile(r'上架时间', re.IGNORECASE))
            if launch_label:
                parent_text = launch_label.parent.get_text(" ", strip=True) if launch_label.parent else ""
                date_match = re.search(r'(\d{4}-\d{1,2}-\d{1,2})', parent_text)
                if date_match:
                    return date_match.group(1)
            
            return None
        except Exception as e:
            logger.error(f"提取上架时间失败: {e}")
            return None
    
    def extract_variant_count(self, soup: BeautifulSoup) -> Optional[int]:
        """提取变体数量"""
        try:
            # 方法1: 查找变体选择器
            variant_selectors = [
                'li.swatchElement',  # 颜色/尺寸变体
                'ul.a-unordered-list.a-nostyle.a-button-list li',
                '#variation_color_name li',
                '#variation_size_name li',
            ]
            
            max_count = 0
            for selector in variant_selectors:
                variants = soup.select(selector)
                if len(variants) > max_count:
                    max_count = len(variants)
            
            if max_count > 0:
                return max_count
            
            # 方法2: 从文本中提取 "X styles available"
            style_text = soup.find(string=re.compile(r'\d+\s+styles?\s+available', re.IGNORECASE))
            if style_text:
                match = re.search(r'(\d+)', style_text)
                if match:
                    return int(match.group(1))
            
            return None
        except Exception as e:
            logger.error(f"提取变体数量失败: {e}")
            return None
    
    def extract_best_selling_color(self, soup: BeautifulSoup) -> Optional[str]:
        """提取畅销颜色"""
        try:
            # 查找当前选中的颜色变体
            selected_variant = soup.find('li', class_=re.compile(r'swatchElement.*selected'))
            if selected_variant:
                color_title = selected_variant.get('title')
                if color_title:
                    # 提取颜色名称 "Click to select Red" -> "Red"
                    match = re.search(r'select\s+(.+)$', color_title, re.IGNORECASE)
                    if match:
                        return match.group(1).strip()
                    return color_title.strip()
            
            # 备用方法：查找颜色选择器中的第一个
            color_variant = soup.find('li', class_='swatchElement')
            if color_variant:
                color_title = color_variant.get('title')
                if color_title:
                    match = re.search(r'select\s+(.+)$', color_title, re.IGNORECASE)
                    if match:
                        return match.group(1).strip()
                    return color_title.strip()
            
            return None
        except Exception as e:
            logger.error(f"提取畅销颜色失败: {e}")
            return None
    
    def extract_bullet_points(self, soup: BeautifulSoup) -> List[str]:
        """提取卖点（bullet points）"""
        try:
            bullet_points = []
            
            # 查找feature bullets
            feature_div = soup.find('div', id='feature-bullets')
            if feature_div:
                bullets = feature_div.find_all('span', class_='a-list-item')
                for bullet in bullets:
                    text = bullet.get_text(strip=True)
                    if text and len(text) > 10:  # 过滤太短的文本
                        bullet_points.append(text)
            
            # 备用方法：查找ul中的li
            if not bullet_points:
                feature_list = soup.find('ul', class_=re.compile(r'a-unordered-list.*a-vertical'))
                if feature_list:
                    bullets = feature_list.find_all('li')
                    for bullet in bullets:
                        text = bullet.get_text(strip=True)
                        if text and len(text) > 10:
                            bullet_points.append(text)
            
            return bullet_points
        except Exception as e:
            logger.error(f"提取卖点失败: {e}")
            return []
    
    def crawl_product_data(self, asin: str, domain: str = 'us') -> Dict[str, Any]:
        """
        爬取产品完整数据
        
        Args:
            asin: 产品ASIN
            domain: Amazon域名
        
        Returns:
            产品数据字典
        """
        logger.info(f"开始爬取产品数据: {asin}")
        
        product_data = {
            'asin': asin,
            'link': None,
            'main_image': None,
            'brand': None,
            'title': None,
            'price': None,
            'promo_price': None,
            'rating': None,
            'review_count': None,
            'bsr_rank': None,
            'main_category': None,
            'main_category_rank': None,
            'sub_category': None,
            'sub_category_rank': None,
            'launch_date': None,
            'variant_count': None,
            'best_selling_color': None,
            'bullet_points': [],
            'monthly_sales_30d': None,  # 需要第三方数据
            'best_monthly_sales': None,  # 需要第三方数据
            'crawl_time': datetime.now().isoformat(),
            'status': 'success',
            'error': None
        }
        
        try:
            # 1. 构建URL
            product_url = self._build_product_url(asin, domain)
            product_data['link'] = product_url
            
            # 2. 获取页面HTML（基础版，用于兜底）
            response = self.request_manager.get(product_url)
            if not response:
                product_data['status'] = 'failed'
                product_data['error'] = '获取页面失败'
                return product_data
            
            # 3. 优先使用 Selenium，其次 Playwright，最后使用 requests 的原始 HTML
            html = (
                self._fetch_rendered_html_with_selenium(product_url)
                or self._fetch_rendered_html_with_playwright(product_url)
                or response.text
            )
            
            # 调试：将实际拿到的HTML保存到本地文件，方便检查页面结构是否包含类目信息
            try:
                debug_path = f"debug_{asin}.html"
                with open(debug_path, "w", encoding="utf-8") as f:
                    f.write(html)
                logger.info(f"[DEBUG] 已保存原始HTML到 {debug_path}")
            except Exception as e:
                logger.warning(f"[DEBUG] 保存原始HTML失败: {e}")
            
            if self._is_captcha_page(html):
                product_data['status'] = 'failed'
                product_data['error'] = '遭遇验证码拦截'
                return product_data
            
            soup = BeautifulSoup(html, 'html.parser')
            
            # 4. 提取各个字段
            product_data['main_image'] = self.extract_main_image(soup)
            product_data['brand'] = self.extract_brand(soup)
            product_data['title'] = self.extract_title(soup)
            product_data['price'] = self.extract_price(soup)
            product_data['promo_price'] = self.extract_promo_price(soup)
            product_data['rating'] = self.extract_rating(soup)
            product_data['review_count'] = self.extract_review_count(soup)
            product_data['bsr_rank'] = self.extract_bsr_ranking(soup)
            
            # 类目排名
            category_rankings = self.extract_category_rankings(soup)
            product_data.update(category_rankings)
            
            product_data['launch_date'] = self.extract_launch_date(soup)
            product_data['variant_count'] = self.extract_variant_count(soup)
            product_data['best_selling_color'] = self.extract_best_selling_color(soup)
            product_data['bullet_points'] = self.extract_bullet_points(soup)
            
            logger.info(f"成功爬取产品数据: {asin}")
            
        except Exception as e:
            logger.exception(f"爬取产品数据失败 {asin}: {e}")
            product_data['status'] = 'failed'
            product_data['error'] = str(e)
        
        return product_data
    
    def batch_crawl(self, asin_list: List[str], domain: str = 'us') -> List[Dict[str, Any]]:
        """
        批量爬取多个产品的数据
        
        Args:
            asin_list: ASIN列表
            domain: Amazon域名
        
        Returns:
            产品数据列表
        """
        logger.info(f"开始批量爬取，共 {len(asin_list)} 个商品")
        
        all_products = []
        
        for i, asin in enumerate(asin_list, 1):
            logger.info(f"正在处理商品 {i}/{len(asin_list)}: {asin}")
            
            product_data = self.crawl_product_data(asin=asin, domain=domain)
            all_products.append(product_data)
            
            # 添加延迟避免被封
            if i < len(asin_list):
                time.sleep(2)
        
        logger.info(f"批量爬取完成，成功: {sum(1 for p in all_products if p['status'] == 'success')} 个")
        
        return all_products
