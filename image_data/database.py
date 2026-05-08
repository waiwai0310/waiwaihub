"""
Database Manager - 管理下载历史和去重
"""
import sqlite3
import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional
from contextlib import contextmanager
import config


class DatabaseManager:
    """管理爬虫数据库,记录下载历史,防止重复下载"""
    
    def __init__(self, db_path: Path = config.DB_PATH):
        self.db_path = db_path
        self._init_database()
    
    def _init_database(self):
        """初始化数据库表结构"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # 产品表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS products (
                    asin TEXT PRIMARY KEY,
                    title TEXT,
                    url TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # 图片下载记录表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS image_downloads (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    asin TEXT NOT NULL,
                    image_url TEXT NOT NULL,
                    local_path TEXT,
                    status TEXT,  -- 'success', 'failed', 'skipped'
                    file_size INTEGER,
                    error_message TEXT,
                    download_time REAL,  -- 下载耗时(秒)
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (asin) REFERENCES products(asin),
                    UNIQUE(asin, image_url)
                )
            ''')
            
            # 请求日志表(用于监控和限流)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS request_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT NOT NULL,
                    status_code INTEGER,
                    response_time REAL,
                    error_type TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # 创建索引
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_downloads_asin 
                ON image_downloads(asin)
            ''')
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_downloads_status 
                ON image_downloads(status)
            ''')
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_requests_time 
                ON request_logs(created_at)
            ''')
            
            conn.commit()
    
    @contextmanager
    def _get_connection(self):
        """获取数据库连接的上下文管理器"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()
    
    def add_product(self, asin: str, title: str = None, url: str = None):
        """添加或更新产品信息"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO products (asin, title, url, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(asin) DO UPDATE SET
                    title = COALESCE(excluded.title, title),
                    url = COALESCE(excluded.url, url),
                    updated_at = excluded.updated_at
            ''', (asin, title, url, datetime.now()))
            conn.commit()
    
    def is_image_downloaded(self, asin: str, image_url: str) -> bool:
        """检查图片是否已成功下载"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id FROM image_downloads
                WHERE asin = ? AND image_url = ? AND status = 'success'
            ''', (asin, image_url))
            return cursor.fetchone() is not None
    
    def record_download(
        self, 
        asin: str, 
        image_url: str, 
        status: str,
        local_path: str = None,
        file_size: int = None,
        error_message: str = None,
        download_time: float = None
    ):
        """记录图片下载结果"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO image_downloads 
                (asin, image_url, local_path, status, file_size, error_message, download_time)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(asin, image_url) DO UPDATE SET
                    local_path = excluded.local_path,
                    status = excluded.status,
                    file_size = excluded.file_size,
                    error_message = excluded.error_message,
                    download_time = excluded.download_time,
                    created_at = CURRENT_TIMESTAMP
            ''', (asin, image_url, local_path, status, file_size, error_message, download_time))
            conn.commit()
    
    def log_request(
        self, 
        url: str, 
        status_code: int = None, 
        response_time: float = None,
        error_type: str = None
    ):
        """记录HTTP请求日志"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO request_logs (url, status_code, response_time, error_type)
                VALUES (?, ?, ?, ?)
            ''', (url, status_code, response_time, error_type))
            conn.commit()
    
    def get_download_stats(self, asin: str = None) -> Dict:
        """获取下载统计信息"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            if asin:
                # 单个产品统计
                cursor.execute('''
                    SELECT 
                        status,
                        COUNT(*) as count,
                        AVG(download_time) as avg_time,
                        SUM(file_size) as total_size
                    FROM image_downloads
                    WHERE asin = ?
                    GROUP BY status
                ''', (asin,))
            else:
                # 全局统计
                cursor.execute('''
                    SELECT 
                        status,
                        COUNT(*) as count,
                        AVG(download_time) as avg_time,
                        SUM(file_size) as total_size
                    FROM image_downloads
                    GROUP BY status
                ''')
            
            stats = {}
            for row in cursor.fetchall():
                stats[row['status']] = {
                    'count': row['count'],
                    'avg_time': row['avg_time'],
                    'total_size': row['total_size']
                }
            
            return stats
    
    def get_recent_errors(self, limit: int = 50) -> List[Dict]:
        """获取最近的错误记录"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT asin, image_url, error_message, created_at
                FROM image_downloads
                WHERE status = 'failed'
                ORDER BY created_at DESC
                LIMIT ?
            ''', (limit,))
            
            return [dict(row) for row in cursor.fetchall()]
    
    def get_request_rate(self, minutes: int = 1) -> float:
        """获取最近N分钟的请求速率"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT COUNT(*) as count
                FROM request_logs
                WHERE created_at > datetime('now', '-' || ? || ' minutes')
            ''', (minutes,))
            
            result = cursor.fetchone()
            return result['count'] / minutes if result else 0
    
    def cleanup_old_logs(self, days: int = 30):
        """清理N天前的日志"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                DELETE FROM request_logs
                WHERE created_at < datetime('now', '-' || ? || ' days')
            ''', (days,))
            deleted = cursor.rowcount
            conn.commit()
            return deleted
