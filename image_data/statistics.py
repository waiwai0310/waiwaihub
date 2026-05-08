"""
下载数据统计分析工具
Analyze download statistics and generate reports
"""
import sys
from pathlib import Path
from database import DatabaseManager
from datetime import datetime, timedelta
import json


def print_section(title: str):
    """打印章节标题"""
    print("\n" + "="*60)
    print(f" {title}")
    print("="*60)


def analyze_download_stats(db_manager: DatabaseManager):
    """分析下载统计"""
    print_section("Overall Download Statistics")
    
    stats = db_manager.get_download_stats()
    
    total_images = sum(s['count'] for s in stats.values())
    total_size = sum(s.get('total_size', 0) or 0 for s in stats.values())
    
    print(f"Total Images: {total_images}")
    print(f"Total Size: {total_size / 1024 / 1024:.2f} MB")
    print()
    
    for status, data in stats.items():
        count = data['count']
        avg_time = data.get('avg_time', 0) or 0
        size = data.get('total_size', 0) or 0
        
        print(f"{status.upper()}:")
        print(f"  Count: {count} ({count/total_images*100:.1f}%)")
        print(f"  Avg Time: {avg_time:.2f}s")
        print(f"  Total Size: {size / 1024 / 1024:.2f} MB")
        print()


def analyze_products(db_manager: DatabaseManager):
    """分析产品统计"""
    print_section("Product Statistics")
    
    with db_manager._get_connection() as conn:
        cursor = conn.cursor()
        
        # 总产品数
        cursor.execute('SELECT COUNT(*) as count FROM products')
        total = cursor.fetchone()['count']
        print(f"Total Products: {total}")
        
        # 有图片的产品数
        cursor.execute('''
            SELECT COUNT(DISTINCT asin) as count 
            FROM image_downloads 
            WHERE status = 'success'
        ''')
        with_images = cursor.fetchone()['count']
        print(f"Products with Images: {with_images}")
        
        # 平均每个产品的图片数
        cursor.execute('''
            SELECT AVG(img_count) as avg_count
            FROM (
                SELECT asin, COUNT(*) as img_count
                FROM image_downloads
                WHERE status = 'success'
                GROUP BY asin
            )
        ''')
        avg = cursor.fetchone()['avg_count'] or 0
        print(f"Avg Images per Product: {avg:.1f}")
        
        # 产品图片数分布
        print("\nImages per Product Distribution:")
        cursor.execute('''
            SELECT img_count, COUNT(*) as products
            FROM (
                SELECT asin, COUNT(*) as img_count
                FROM image_downloads
                WHERE status = 'success'
                GROUP BY asin
            )
            GROUP BY img_count
            ORDER BY img_count
        ''')
        
        for row in cursor.fetchall():
            count = row['img_count']
            products = row['products']
            print(f"  {count} images: {products} products")


def analyze_errors(db_manager: DatabaseManager, limit: int = 10):
    """分析错误统计"""
    print_section(f"Recent Errors (Top {limit})")
    
    errors = db_manager.get_recent_errors(limit)
    
    if not errors:
        print("No errors found!")
        return
    
    for i, error in enumerate(errors, 1):
        print(f"\n{i}. ASIN: {error['asin']}")
        print(f"   Error: {error['error_message']}")
        print(f"   Time: {error['created_at']}")
    
    # 错误类型统计
    print_section("Error Type Distribution")
    
    with db_manager._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT 
                CASE 
                    WHEN error_message LIKE '%timeout%' THEN 'Timeout'
                    WHEN error_message LIKE '%403%' THEN '403 Forbidden'
                    WHEN error_message LIKE '%404%' THEN '404 Not Found'
                    WHEN error_message LIKE '%429%' THEN '429 Rate Limited'
                    ELSE 'Other'
                END as error_type,
                COUNT(*) as count
            FROM image_downloads
            WHERE status = 'failed'
            GROUP BY error_type
            ORDER BY count DESC
        ''')
        
        for row in cursor.fetchall():
            print(f"{row['error_type']}: {row['count']}")


def analyze_request_rate(db_manager: DatabaseManager):
    """分析请求速率"""
    print_section("Request Rate Analysis")
    
    # 最近1小时的请求速率
    rate_1h = db_manager.get_request_rate(60)
    print(f"Requests in last hour: {rate_1h:.1f} req/min")
    
    # 最近5分钟的请求速率
    rate_5m = db_manager.get_request_rate(5)
    print(f"Requests in last 5 min: {rate_5m:.1f} req/min")
    
    # 状态码分布
    with db_manager._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT status_code, COUNT(*) as count
            FROM request_logs
            WHERE created_at > datetime('now', '-1 hour')
            GROUP BY status_code
            ORDER BY count DESC
        ''')
        
        print("\nStatus Code Distribution (last hour):")
        for row in cursor.fetchall():
            code = row['status_code']
            count = row['count']
            if code:
                print(f"  {code}: {count}")


def analyze_top_products(db_manager: DatabaseManager, limit: int = 10):
    """分析下载最多的产品"""
    print_section(f"Top {limit} Products by Image Count")
    
    with db_manager._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT 
                d.asin,
                p.title,
                COUNT(*) as image_count,
                SUM(d.file_size) as total_size
            FROM image_downloads d
            LEFT JOIN products p ON d.asin = p.asin
            WHERE d.status = 'success'
            GROUP BY d.asin
            ORDER BY image_count DESC
            LIMIT ?
        ''', (limit,))
        
        for i, row in enumerate(cursor.fetchall(), 1):
            size_mb = (row['total_size'] or 0) / 1024 / 1024
            title = row['title'] or 'N/A'
            if len(title) > 50:
                title = title[:47] + '...'
            
            print(f"\n{i}. {row['asin']}")
            print(f"   Title: {title}")
            print(f"   Images: {row['image_count']}")
            print(f"   Size: {size_mb:.2f} MB")


def generate_json_report(db_manager: DatabaseManager, output_file: str):
    """生成JSON格式的报告"""
    report = {
        'generated_at': datetime.now().isoformat(),
        'overall_stats': db_manager.get_download_stats(),
    }
    
    # 产品统计
    with db_manager._get_connection() as conn:
        cursor = conn.cursor()
        
        cursor.execute('SELECT COUNT(*) as count FROM products')
        report['total_products'] = cursor.fetchone()['count']
        
        cursor.execute('''
            SELECT COUNT(DISTINCT asin) as count 
            FROM image_downloads 
            WHERE status = 'success'
        ''')
        report['products_with_images'] = cursor.fetchone()['count']
    
    # 保存到文件
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    
    print(f"\nJSON report saved to: {output_file}")


def main():
    """主函数"""
    db_path = Path('data/crawler_db.sqlite')
    
    if not db_path.exists():
        print("Error: Database not found. Please run the crawler first.")
        sys.exit(1)
    
    db_manager = DatabaseManager(db_path)
    
    print("\n" + "🔍 Amazon Image Crawler - Statistics Report".center(60))
    
    analyze_download_stats(db_manager)
    analyze_products(db_manager)
    analyze_top_products(db_manager, 10)
    analyze_errors(db_manager, 10)
    analyze_request_rate(db_manager)
    
    # 询问是否生成JSON报告
    if len(sys.argv) > 1 and sys.argv[1] == '--json':
        output_file = 'data/statistics_report.json'
        generate_json_report(db_manager, output_file)
    
    print("\n" + "="*60)
    print("Tip: Run with --json to generate a JSON report")
    print("="*60 + "\n")


if __name__ == '__main__':
    main()
