"""
Amazon Image Crawler - Main Entry Point
主程序入口
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
from image_downloader import AmazonImageDownloader


def setup_logging():
    """配置日志系统"""
    # 创建日志目录
    config.LOG_DIR.mkdir(parents=True, exist_ok=True)
    
    # 配置根日志记录器
    logging.basicConfig(
        level=getattr(logging, config.LOG_LEVEL),
        format=config.LOG_FORMAT,
        handlers=[
            # 文件处理器(轮转)
            logging.handlers.RotatingFileHandler(
                config.LOG_FILE,
                maxBytes=config.LOG_MAX_BYTES,
                backupCount=config.LOG_BACKUP_COUNT,
                encoding='utf-8'
            ),
            # 控制台处理器
            logging.StreamHandler(sys.stdout)
        ]
    )
    
    # 降低第三方库的日志级别
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('requests').setLevel(logging.WARNING)
    
    logger = logging.getLogger(__name__)
    logger.info("="*60)
    logger.info("亚马逊图片爬虫已启动")
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
        description='Amazon Product Image Crawler - 安全稳定的图片爬取工具',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  # 下载单个产品图片
  python main.py -a B08N5WRWNW
  
  # 下载多个产品图片
  python main.py -a B08N5WRWNW B07XJ8C8F5 B09G9FPHY6
  
  # 从文件读取ASIN列表
  python main.py -f asin_list.txt
  
  # 指定Amazon域名(默认us)
  python main.py -a B08N5WRWNW -d jp
  
  # 指定每个产品最多下载图片数
  python main.py -a B08N5WRWNW -m 5
  
  # 查看下载统计
  python main.py --stats
  
  # 清理旧日志
  python main.py --cleanup-logs 30
        """
    )
    
    # 输入参数
    input_group = parser.add_mutually_exclusive_group(required=False)
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
        '-m', '--max-images',
        type=int,
        default=config.MAX_IMAGES_PER_PRODUCT,
        help=f'每个产品最多下载图片数(默认: {config.MAX_IMAGES_PER_PRODUCT})'
    )
    parser.add_argument(
        '--skip-existing',
        action='store_true',
        default=False,
        help='跳过已下载的图片(默认: False)'
    )
    parser.add_argument(
        '--force-redownload',
        action='store_true',
        help='强制重新下载，忽略已下载记录'
    )
    parser.add_argument(
        '--allow-fallback-images',
        action='store_true',
        help='允许全页兜底抓图(可能混入其他产品图片)'
    )
    
    # 管理命令
    parser.add_argument(
        '--stats',
        action='store_true',
        help='显示下载统计信息'
    )
    parser.add_argument(
        '--cleanup-logs',
        type=int,
        metavar='DAYS',
        help='清理N天前的请求日志'
    )
    parser.add_argument(
        '--recent-errors',
        type=int,
        metavar='LIMIT',
        default=None,
        help='显示最近的错误记录'
    )
    
    args = parser.parse_args()
    
    # 设置日志
    setup_logging()
    logger = logging.getLogger(__name__)
    
    # 初始化组件
    db_manager = DatabaseManager()
    request_manager = RequestManager(db_manager)
    downloader = AmazonImageDownloader(request_manager, db_manager)
    
    try:
        # 处理管理命令
        if args.stats:
            stats = db_manager.get_download_stats()
            logger.info("下载统计:")
            status_zh = {
                'success': '成功',
                'failed': '失败',
                'skipped': '跳过',
            }
            for status, data in stats.items():
                label = status_zh.get(status, status)
                logger.info(f"  {label}: {data['count']} 张图片, "
                          f"平均耗时: {data['avg_time']:.2f}s, "
                          f"总大小: {data['total_size'] / 1024 / 1024:.2f}MB")
            return
        
        if args.cleanup_logs:
            deleted = db_manager.cleanup_old_logs(args.cleanup_logs)
            logger.info(f"已清理 {deleted} 条旧日志记录")
            return
        
        if args.recent_errors is not None:
            errors = db_manager.get_recent_errors(args.recent_errors)
            logger.info(f"最近 {len(errors)} 条错误:")
            for error in errors:
                logger.info(f"  {error['asin']}: {error['error_message']} ({error['created_at']})")
            return
        
        # 获取ASIN列表
        asin_list = []
        if args.asin:
            asin_list = args.asin
        elif args.file:
            asin_list = read_asin_from_file(args.file)
        else:
            parser.print_help()
            return
        
        if not asin_list:
            logger.error("未提供 ASIN")
            return
        
        logger.info(f"正在处理 {len(asin_list)} 个商品")
        
        # 批量下载
        all_stats = downloader.batch_download(
            asin_list=asin_list,
            domain=args.domain,
            max_images_per_product=args.max_images,
            skip_existing=(args.skip_existing and not args.force_redownload),
            strict_product_images=(not args.allow_fallback_images),
        )
        
        # 输出汇总
        logger.info("="*60)
        logger.info("下载汇总:")
        logger.info(f"  商品总数: {len(asin_list)}")
        logger.info(f"  图片总数: {sum(s['total'] for s in all_stats)}")
        logger.info(f"  成功数: {sum(s['success'] for s in all_stats)}")
        logger.info(f"  失败数: {sum(s['failed'] for s in all_stats)}")
        logger.info(f"  跳过数: {sum(s['skipped'] for s in all_stats)}")
        logger.info("="*60)
        
        # 显示失败的产品
        failed_products = [s for s in all_stats if s['failed'] > 0 or s['total'] == 0]
        if failed_products:
            logger.warning(f"存在失败的商品数: {len(failed_products)}")
            for stat in failed_products:
                logger.warning(f"  {stat['asin']}: 失败 {stat['failed']} 张, 错误 {len(stat['errors'])} 条")
    
    except KeyboardInterrupt:
        logger.info("用户中断执行")
    except Exception as e:
        logger.exception(f"发生未预期异常: {e}")
    finally:
        request_manager.close()
        logger.info("爬虫已完成关闭")


if __name__ == '__main__':
    main()
