"""
演示脚本 - 使用模拟数据展示Excel输出功能
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from excel_exporter import ExcelExporter
from datetime import datetime

# 创建模拟的产品数据
mock_products = [
    {
        'asin': 'B08N5WRWNW',
        'main_image': 'https://m.media-amazon.com/images/I/71abc123.jpg',
        'brand': 'Amazon Basics',
        'title': 'Amazon Basics Classic Office Desk Chair with Arms, Low Back, Adjustable, Black',
        'link': 'https://www.amazon.com/dp/B08N5WRWNW',
        'price': '$89.99',
        'promo_price': '$79.99',
        'rating': 4.5,
        'review_count': 12543,
        'bsr_rank': '1,234',
        'main_category': 'Office Products',
        'main_category_rank': '15',
        'sub_category': 'Home Office Desk Chairs',
        'sub_category_rank': '3',
        'launch_date': 'January 15, 2021',
        'variant_count': 5,
        'best_selling_color': 'Black',
        'monthly_sales_30d': None,  # 需要第三方工具
        'best_monthly_sales': None,  # 需要第三方工具
        'bullet_points': [
            'ADJUSTABLE HEIGHT: Pneumatic seat-height adjustment; height range: 18.5-22.5 inches',
            'SMOOTH MOVEMENT: 360-degree swivel; easy-roll casters for mobility',
            'SUPPORTIVE DESIGN: Padded seat and back for comfortable support',
            'DURABLE BUILD: Sturdy 5-star base with 275-pound weight capacity',
            'EASY ASSEMBLY: Ships ready to assemble with step-by-step instructions'
        ],
        'crawl_time': datetime.now().isoformat(),
        'status': 'success',
        'error': None
    },
    {
        'asin': 'B07XJ8C8F5',
        'main_image': 'https://m.media-amazon.com/images/I/81def456.jpg',
        'brand': 'Logitech',
        'title': 'Logitech MX Master 3 Advanced Wireless Mouse - Graphite',
        'link': 'https://www.amazon.com/dp/B07XJ8C8F5',
        'price': '$99.99',
        'promo_price': None,
        'rating': 4.7,
        'review_count': 23891,
        'bsr_rank': '456',
        'main_category': 'Electronics',
        'main_category_rank': '8',
        'sub_category': 'Computer Accessories & Peripherals',
        'sub_category_rank': '2',
        'launch_date': 'May 20, 2019',
        'variant_count': 3,
        'best_selling_color': 'Graphite',
        'monthly_sales_30d': None,
        'best_monthly_sales': None,
        'bullet_points': [
            'MAGSPEED WHEEL: Ultra-fast scrolling or ratchet precision',
            'DARKFIELD TRACKING: Works on any surface, even glass',
            'FLOW CROSS-COMPUTER CONTROL: Control multiple computers seamlessly',
            'EASY-SWITCH: Connect up to 3 devices via Bluetooth or USB receiver',
            'RECHARGEABLE: 70 days on full charge, quick charging (3 min = 8 hrs use)'
        ],
        'crawl_time': datetime.now().isoformat(),
        'status': 'success',
        'error': None
    },
    {
        'asin': 'B09G9FPHY6',
        'main_image': 'https://m.media-amazon.com/images/I/91ghi789.jpg',
        'brand': 'Apple',
        'title': 'Apple AirPods (3rd Generation) with MagSafe Charging Case',
        'link': 'https://www.amazon.com/dp/B09G9FPHY6',
        'price': '$169.99',
        'promo_price': '$149.99',
        'rating': 4.6,
        'review_count': 8765,
        'bsr_rank': '89',
        'main_category': 'Electronics',
        'main_category_rank': '3',
        'sub_category': 'Earbud Headphones',
        'sub_category_rank': '1',
        'launch_date': 'October 18, 2021',
        'variant_count': 1,
        'best_selling_color': None,
        'monthly_sales_30d': None,
        'best_monthly_sales': None,
        'bullet_points': [
            'SPATIAL AUDIO: Surround sound with dynamic head tracking',
            'ADAPTIVE EQ: Music automatically tuned to your ears',
            'LONG BATTERY LIFE: Up to 6 hours listening time, 30 hours with case',
            'SWEAT AND WATER RESISTANT: IPX4-rated',
            'EASY SETUP: Magical connection to all your Apple devices'
        ],
        'crawl_time': datetime.now().isoformat(),
        'status': 'success',
        'error': None
    },
    {
        'asin': 'B0TESTFAIL',
        'main_image': None,
        'brand': None,
        'title': None,
        'link': 'https://www.amazon.com/dp/B0TESTFAIL',
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
        'monthly_sales_30d': None,
        'best_monthly_sales': None,
        'bullet_points': [],
        'crawl_time': datetime.now().isoformat(),
        'status': 'failed',
        'error': '遭遇验证码拦截'
    }
]

def main():
    print("="*60)
    print("Amazon产品数据爬虫 - 演示模式")
    print("="*60)
    print(f"\n模拟爬取了 {len(mock_products)} 个产品")
    print(f"成功: {sum(1 for p in mock_products if p['status'] == 'success')} 个")
    print(f"失败: {sum(1 for p in mock_products if p['status'] != 'success')} 个")
    
    # 导出到Excel
    exporter = ExcelExporter(output_dir=Path('data'))
    output_path = exporter.export_with_summary(
        products=mock_products,
        filename='demo_products.xlsx'
    )
    
    print(f"\n✅ 演示数据已导出到: {output_path}")
    print("\n输出的Excel包含:")
    print("  📊 Sheet 1: Summary - 汇总统计信息")
    print("  📋 Sheet 2: Products - 详细产品数据")
    print("\n" + "="*60)
    print("提示: 这是使用模拟数据的演示版本")
    print("真实爬取请运行: python crawl_product_data.py -f asin_list.txt")
    print("="*60)

if __name__ == '__main__':
    main()
