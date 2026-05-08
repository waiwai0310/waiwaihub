"""
Product Data Crawler - Main Entry Point
产品数据爬取主程序
"""
import logging
import logging.handlers
import argparse
import sys
from pathlib import Path
from typing import List
import config
from database import DatabaseManager
from request_manager import RequestManager
from product_data_crawler import ProductDataCrawler
from excel_exporter import ExcelExporter


def setup_logging():
    """配置日志系统"""
    config.LOG_DIR.mkdir(parents=True, exist_ok=True)
    
    logging.basicConfig(
        # 为了调试类目排名等问题，这里强制使用 DEBUG 级别，方便查看详细日志
        level=logging.DEBUG,
        format=config.LOG_FORMAT,
        handlers=[
            logging.handlers.RotatingFileHandler(
                config.LOG_FILE,
                maxBytes=config.LOG_MAX_BYTES,
                backupCount=config.LOG_BACKUP_COUNT,
                encoding='utf-8'
            ),
            logging.StreamHandler(sys.stdout)
        ]
    )
    
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('requests').setLevel(logging.WARNING)
    
    logger = logging.getLogger(__name__)
    logger.info("="*60)
    logger.info("亚马逊产品数据爬虫已启动")
    logger.info("="*60)


def read_asin_from_file(filepath: str) -> List[str]:
    """从文件读取ASIN列表(每行一个)"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            asins = [line.strip() for line in f if line.strip()]
        return asins
    except Exception as e:
        logging.error(f"读取 ASIN 文件失败: {e}")
        return []


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description='Amazon Product Data Crawler - 亚马逊产品数据爬虫',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  # 爬取单个产品数据
  python crawl_product_data.py -a B08N5WRWNW
  
  # 爬取多个产品数据
  python crawl_product_data.py -a B08N5WRWNW B07XJ8C8F5 B09G9FPHY6
  
  # 从文件读取ASIN列表
  python crawl_product_data.py -f asin_list.txt
  
  # 指定输出文件名
  python crawl_product_data.py -a B08N5WRWNW -o my_products.xlsx
  
  # 指定Amazon域名(默认us)
  python crawl_product_data.py -a B08N5WRWNW -d jp
        """
    )
    
    # 输入参数
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument(
        '-a', '--asin',
        nargs='+',
        help='产品ASIN(可以是多个,空格分隔)'
    )
    input_group.add_argument(
        '-f', '--file',
        help='包含ASIN列表的文件路径(每行一个ASIN)'
    )
    
    # 配置参数
    parser.add_argument(
        '-d', '--domain',
        default='us',
        choices=list(config.AMAZON_DOMAINS.keys()),
        help='Amazon域名(默认: us)'
    )
    parser.add_argument(
        '-o', '--output',
        help='输出Excel文件名(默认使用时间戳)'
    )
    parser.add_argument(
        '--no-summary',
        action='store_true',
        help='不生成汇总统计sheet'
    )
    parser.add_argument(
        '--output-dir',
        default='data',
        help='输出目录(默认: data/)'
    )
    
    args = parser.parse_args()
    
    # 设置日志
    setup_logging()
    logger = logging.getLogger(__name__)
    
    # 初始化组件
    db_manager = DatabaseManager()
    request_manager = RequestManager(db_manager)
    crawler = ProductDataCrawler(request_manager, db_manager)
    exporter = ExcelExporter(output_dir=Path(args.output_dir))
    
    try:
        # 获取ASIN列表
        asin_list = []
        if args.asin:
            asin_list = args.asin
        elif args.file:
            asin_list = read_asin_from_file(args.file)
        
        if not asin_list:
            logger.error("未提供 ASIN")
            return
        
        logger.info(f"正在处理 {len(asin_list)} 个商品")
        
        # 批量爬取
        products = crawler.batch_crawl(
            asin_list=asin_list,
            domain=args.domain
        )
        
        # 输出统计
        success_count = sum(1 for p in products if p['status'] == 'success')
        failed_count = len(products) - success_count
        
        logger.info("="*60)
        logger.info("爬取汇总:")
        logger.info(f"  商品总数: {len(products)}")
        logger.info(f"  成功: {success_count}")
        logger.info(f"  失败: {failed_count}")
        logger.info("="*60)
        
        # 显示失败的产品
        failed_products = [p for p in products if p['status'] != 'success']
        if failed_products:
            logger.warning(f"失败的商品:")
            for product in failed_products:
                logger.warning(f"  {product['asin']}: {product.get('error', 'Unknown error')}")
        
        # 导出到Excel
        if products:
            if args.no_summary:
                output_path = exporter.export(products, filename=args.output)
            else:
                output_path = exporter.export_with_summary(products, filename=args.output)
            
            if output_path:
                logger.info(f"数据已导出到: {output_path}")
        else:
            logger.warning("没有数据可导出")
    
    except KeyboardInterrupt:
        logger.info("用户中断执行")
    except Exception as e:
        logger.exception(f"发生未预期异常: {e}")
    finally:
        request_manager.close()
        logger.info("爬虫已完成关闭")


if __name__ == '__main__':
    main()
