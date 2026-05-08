"""
图片完整性验证工具
Verify downloaded images for corruption
"""
import sys
from pathlib import Path
from PIL import Image
import logging

logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def verify_image(image_path: Path) -> tuple[bool, str]:
    """
    验证单个图片文件
    
    Returns:
        (是否有效, 错误信息)
    """
    try:
        with Image.open(image_path) as img:
            img.verify()
        
        # 重新打开检查基本属性
        with Image.open(image_path) as img:
            width, height = img.size
            if width < 100 or height < 100:
                return False, f"Image too small: {width}x{height}"
        
        return True, None
    except Exception as e:
        return False, str(e)


def verify_images_in_directory(image_dir: str):
    """验证目录中的所有图片"""
    image_dir = Path(image_dir)
    
    if not image_dir.exists():
        logger.error(f"Directory not found: {image_dir}")
        return
    
    logger.info(f"Scanning directory: {image_dir}")
    
    stats = {
        'total': 0,
        'valid': 0,
        'corrupt': 0,
        'too_small': 0,
    }
    
    corrupt_files = []
    
    # 支持的图片格式
    image_extensions = ['.jpg', '.jpeg', '.png', '.webp']
    
    for ext in image_extensions:
        for image_path in image_dir.rglob(f'*{ext}'):
            stats['total'] += 1
            
            valid, error = verify_image(image_path)
            
            if valid:
                stats['valid'] += 1
            else:
                stats['corrupt'] += 1
                corrupt_files.append((image_path, error))
                if 'too small' in error.lower():
                    stats['too_small'] += 1
    
    # 输出报告
    logger.info("="*60)
    logger.info("Verification Report:")
    logger.info(f"  Total Images: {stats['total']}")
    logger.info(f"  Valid: {stats['valid']} ({stats['valid']/stats['total']*100:.1f}%)")
    logger.info(f"  Corrupt: {stats['corrupt']} ({stats['corrupt']/stats['total']*100:.1f}%)")
    logger.info(f"  Too Small: {stats['too_small']}")
    logger.info("="*60)
    
    if corrupt_files:
        logger.warning(f"\nFound {len(corrupt_files)} corrupt files:")
        for file_path, error in corrupt_files[:20]:  # 只显示前20个
            logger.warning(f"  {file_path.name}: {error}")
        
        if len(corrupt_files) > 20:
            logger.warning(f"  ... and {len(corrupt_files) - 20} more")
        
        # 询问是否删除损坏的文件
        if input("\nDelete corrupt files? (y/N): ").lower() == 'y':
            for file_path, _ in corrupt_files:
                file_path.unlink()
                logger.info(f"Deleted: {file_path}")
    
    return stats


def main():
    """主函数"""
    if len(sys.argv) > 1:
        image_dir = sys.argv[1]
    else:
        image_dir = 'data/images'
    
    verify_images_in_directory(image_dir)


if __name__ == '__main__':
    main()
