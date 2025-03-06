import logging
import traceback
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
import threading
from collections import defaultdict
import json
from django.core.cache import cache
from django.conf import settings

logger = logging.getLogger(__name__)

class ErrorTracker:
    """错误追踪器"""
    
    _instance = None
    _lock = threading.Lock()
    
    # 缓存键
    ERROR_STATS_KEY = "error_tracker:stats"
    ERROR_HISTORY_KEY = "error_tracker:history"
    
    # 默认保留时间（天）
    DEFAULT_RETENTION_DAYS = 7
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialize()
        return cls._instance
    
    def _initialize(self):
        """初始化追踪器"""
        self.error_stats = defaultdict(lambda: {
            'count': 0,
            'first_seen': None,
            'last_seen': None,
            'occurrences': []
        })
        self.load_from_cache()
    
    def track_error(self, error: Exception, context: Dict[str, Any] = None) -> None:
        """追踪错误"""
        try:
            error_type = type(error).__name__
            error_message = str(error)
            stack_trace = traceback.format_exc()
            
            timestamp = datetime.now()
            
            with self._lock:
                # 更新错误统计
                if error_type not in self.error_stats:
                    self.error_stats[error_type] = {
                        'count': 0,
                        'first_seen': timestamp,
                        'last_seen': timestamp,
                        'occurrences': []
                    }
                
                stats = self.error_stats[error_type]
                stats['count'] += 1
                stats['last_seen'] = timestamp
                
                # 添加错误记录
                occurrence = {
                    'timestamp': timestamp.isoformat(),
                    'message': error_message,
                    'stack_trace': stack_trace,
                    'context': context or {}
                }
                
                # 保持最近的错误记录
                max_occurrences = getattr(settings, 'ERROR_TRACKER_MAX_OCCURRENCES', 100)
                stats['occurrences'].append(occurrence)
                if len(stats['occurrences']) > max_occurrences:
                    stats['occurrences'].pop(0)
                
                # 保存到缓存
                self.save_to_cache()
                
                # 记录到日志
                logger.error(
                    f"Error tracked - Type: {error_type}, Message: {error_message}",
                    extra={
                        'error_type': error_type,
                        'error_message': error_message,
                        'stack_trace': stack_trace,
                        'context': context
                    }
                )
                
        except Exception as e:
            logger.error(f"Error in track_error: {str(e)}")
    
    def get_error_stats(self) -> Dict[str, Any]:
        """获取错误统计信息"""
        with self._lock:
            return {
                error_type: {
                    'count': stats['count'],
                    'first_seen': stats['first_seen'].isoformat() if stats['first_seen'] else None,
                    'last_seen': stats['last_seen'].isoformat() if stats['last_seen'] else None,
                    'recent_occurrences': stats['occurrences'][-5:]  # 只返回最近5条记录
                }
                for error_type, stats in self.error_stats.items()
            }
    
    def get_error_history(self, error_type: str = None, days: int = 7) -> List[Dict[str, Any]]:
        """获取错误历史记录"""
        with self._lock:
            cutoff_date = datetime.now() - timedelta(days=days)
            
            if error_type:
                if error_type not in self.error_stats:
                    return []
                
                return [
                    occurrence
                    for occurrence in self.error_stats[error_type]['occurrences']
                    if datetime.fromisoformat(occurrence['timestamp']) > cutoff_date
                ]
            
            # 返回所有类型的错误
            all_occurrences = []
            for stats in self.error_stats.values():
                all_occurrences.extend([
                    occurrence
                    for occurrence in stats['occurrences']
                    if datetime.fromisoformat(occurrence['timestamp']) > cutoff_date
                ])
            
            # 按时间排序
            return sorted(
                all_occurrences,
                key=lambda x: x['timestamp'],
                reverse=True
            )
    
    def clear_old_errors(self, days: int = None) -> None:
        """清除旧的错误记录"""
        if days is None:
            days = self.DEFAULT_RETENTION_DAYS
        
        cutoff_date = datetime.now() - timedelta(days=days)
        
        with self._lock:
            for error_type in list(self.error_stats.keys()):
                stats = self.error_stats[error_type]
                
                # 过滤掉旧的记录
                stats['occurrences'] = [
                    occurrence
                    for occurrence in stats['occurrences']
                    if datetime.fromisoformat(occurrence['timestamp']) > cutoff_date
                ]
                
                # 如果没有记录了，删除这个错误类型
                if not stats['occurrences']:
                    del self.error_stats[error_type]
                else:
                    # 更新首次和最后出现时间
                    stats['first_seen'] = datetime.fromisoformat(stats['occurrences'][0]['timestamp'])
                    stats['last_seen'] = datetime.fromisoformat(stats['occurrences'][-1]['timestamp'])
            
            # 保存到缓存
            self.save_to_cache()
    
    def save_to_cache(self) -> None:
        """保存数据到缓存"""
        try:
            # 序列化数据
            cache_data = {
                error_type: {
                    'count': stats['count'],
                    'first_seen': stats['first_seen'].isoformat() if stats['first_seen'] else None,
                    'last_seen': stats['last_seen'].isoformat() if stats['last_seen'] else None,
                    'occurrences': stats['occurrences']
                }
                for error_type, stats in self.error_stats.items()
            }
            
            # 保存到缓存
            cache.set(self.ERROR_STATS_KEY, json.dumps(cache_data), timeout=None)
            
        except Exception as e:
            logger.error(f"Error saving to cache: {str(e)}")
    
    def load_from_cache(self) -> None:
        """从缓存加载数据"""
        try:
            cache_data = cache.get(self.ERROR_STATS_KEY)
            if not cache_data:
                return
            
            data = json.loads(cache_data)
            
            with self._lock:
                for error_type, stats in data.items():
                    self.error_stats[error_type] = {
                        'count': stats['count'],
                        'first_seen': datetime.fromisoformat(stats['first_seen']) if stats['first_seen'] else None,
                        'last_seen': datetime.fromisoformat(stats['last_seen']) if stats['last_seen'] else None,
                        'occurrences': stats['occurrences']
                    }
                    
        except Exception as e:
            logger.error(f"Error loading from cache: {str(e)}")
    
    def get_error_summary(self) -> Dict[str, Any]:
        """获取错误摘要"""
        with self._lock:
            total_errors = sum(stats['count'] for stats in self.error_stats.values())
            
            return {
                'total_errors': total_errors,
                'unique_errors': len(self.error_stats),
                'error_types': {
                    error_type: stats['count']
                    for error_type, stats in self.error_stats.items()
                },
                'recent_errors': self.get_error_history(days=1)[:10]  # 最近24小时的前10条错误
            }
    
    @classmethod
    def get_instance(cls) -> 'ErrorTracker':
        """获取追踪器实例"""
        return cls() 