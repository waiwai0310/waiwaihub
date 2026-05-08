"""
日志管理模块
负责日志记录和错误追踪
"""

import os
import datetime
from typing import List, Optional


class Logger:
    """日志管理器"""
    
    def __init__(self, log_file: str):
        """
        初始化日志管理器
        
        Args:
            log_file: 日志文件名
        """
        # 允许配置传入相对路径：相对基准为本文件所在目录
        if os.path.isabs(log_file):
            self.log_file = log_file
        else:
            self.log_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), log_file)
        self.messages = []
        self.errors = []
    
    def log(self, message: str, level: str = "INFO"):
        """
        记录日志消息
        
        Args:
            message: 日志内容
            level: 日志级别 (INFO, WARNING, ERROR)
        """
        timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        formatted_msg = f"[{timestamp}] [{level}] {message}"
        
        self.messages.append(formatted_msg)
        
        # 同时打印到控制台
        if level == "ERROR":
            print(f"❌ {message}")
            self.errors.append(message)
        elif level == "WARNING":
            print(f"⚠️  {message}")
        else:
            print(f"ℹ️  {message}")
    
    def error(self, message: str):
        """记录错误"""
        self.log(message, "ERROR")
    
    def warning(self, message: str):
        """记录警告"""
        self.log(message, "WARNING")
    
    def info(self, message: str):
        """记录信息"""
        self.log(message, "INFO")
    
    def flush(self) -> bool:
        """
        将日志写入文件
        
        Returns:
            是否成功
        """
        if not self.messages:
            return True
        
        try:
            # 如果日志路径包含子目录（如 output/error_log.txt），先创建目录
            log_dir = os.path.dirname(self.log_file)
            if log_dir:
                os.makedirs(log_dir, exist_ok=True)

            with open(self.log_file, 'a', encoding='utf-8') as f:
                f.write('\n'.join(self.messages) + '\n')
            
            self.messages = []
            return True
        
        except Exception as e:
            print(f"❌ 日志写入失败: {e}")
            return False
    
    def get_summary(self) -> dict:
        """
        获取日志摘要
        
        Returns:
            包含统计信息的字典
        """
        return {
            'total_messages': len(self.messages),
            'total_errors': len(self.errors),
            'log_file': self.log_file
        }
    
    def __del__(self):
        """析构函数：确保日志被写入"""
        self.flush()
    
    def __enter__(self):
        """上下文管理器支持"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器支持"""
        self.flush()
