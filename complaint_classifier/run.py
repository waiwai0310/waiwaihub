"""
快速启动脚本
直接运行此文件即可启动客诉分类系统
"""

import sys
import os

# 添加当前目录到 Python 路径
sys.path.insert(0, os.path.dirname(__file__))

from main import main

if __name__ == "__main__":
    main()
