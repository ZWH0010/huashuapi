import time
import logging
import threading
from functools import wraps
from typing import Dict, Any, Optional
from django.db import connection
from django.conf import settings
from collections import defaultdict
import psutil
import os

logger = logging.getLogger(__name__)

class PerformanceMonitor:
    """性能监控器"""
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialize()
        return cls._instance
    
    def _initialize(self):
        """初始化监控器"""
        self.metrics = defaultdict(lambda: {
            'count': 0,
            'total_time': 0,
            'min_time': float('inf'),
            'max_time': 0,
            'avg_time': 0
        })
        self.db_metrics = defaultdict(lambda: {
            'count': 0,
            'total_time': 0,
            'queries': 0
        })
        self.process = psutil.Process(os.getpid())
        self._start_time = time.time()
    
    def monitor_performance(self, operation_name: str):
        """性能监控装饰器"""
        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                start_time = time.time()
                start_queries = len(connection.queries)
                
                try:
                    result = func(*args, **kwargs)
                    return result
                finally:
                    end_time = time.time()
                    execution_time = end_time - start_time
                    
                    # 更新操作指标
                    with self._lock:
                        metrics = self.metrics[operation_name]
                        metrics['count'] += 1
                        metrics['total_time'] += execution_time
                        metrics['min_time'] = min(metrics['min_time'], execution_time)
                        metrics['max_time'] = max(metrics['max_time'], execution_time)
                        metrics['avg_time'] = metrics['total_time'] / metrics['count']
                    
                    # 更新数据库指标
                    end_queries = len(connection.queries)
                    queries_executed = end_queries - start_queries
                    
                    with self._lock:
                        db_metrics = self.db_metrics[operation_name]
                        db_metrics['count'] += 1
                        db_metrics['total_time'] += execution_time
                        db_metrics['queries'] += queries_executed
                    
                    # 记录慢操作
                    threshold = getattr(settings, 'SLOW_OPERATION_THRESHOLD', 1.0)
                    if execution_time > threshold:
                        logger.warning(
                            f"Slow operation detected: {operation_name} "
                            f"took {execution_time:.2f} seconds "
                            f"and executed {queries_executed} queries"
                        )
            
            return wrapper
        return decorator
    
    def get_performance_metrics(self) -> Dict[str, Any]:
        """获取性能指标"""
        with self._lock:
            return {
                'operations': dict(self.metrics),
                'database': dict(self.db_metrics),
                'system': self.get_system_metrics(),
                'uptime': time.time() - self._start_time
            }
    
    def get_system_metrics(self) -> Dict[str, Any]:
        """获取系统指标"""
        try:
            memory_info = self.process.memory_info()
            cpu_percent = self.process.cpu_percent(interval=1)
            
            return {
                'memory_usage': {
                    'rss': memory_info.rss,  # 物理内存使用
                    'vms': memory_info.vms,  # 虚拟内存使用
                    'percent': self.process.memory_percent()
                },
                'cpu_usage': {
                    'percent': cpu_percent,
                    'threads': len(self.process.threads())
                },
                'io_counters': self.process.io_counters()._asdict(),
                'connections': len(self.process.connections())
            }
        except Exception as e:
            logger.error(f"Error getting system metrics: {str(e)}")
            return {}
    
    def reset_metrics(self) -> None:
        """重置所有指标"""
        with self._lock:
            self.metrics.clear()
            self.db_metrics.clear()
            self._start_time = time.time()
    
    def get_slow_operations(self, threshold: float = None) -> Dict[str, Any]:
        """获取慢操作列表"""
        if threshold is None:
            threshold = getattr(settings, 'SLOW_OPERATION_THRESHOLD', 1.0)
        
        with self._lock:
            return {
                name: metrics
                for name, metrics in self.metrics.items()
                if metrics['avg_time'] > threshold
            }
    
    def get_database_stats(self) -> Dict[str, Any]:
        """获取数据库统计信息"""
        with self._lock:
            total_queries = sum(m['queries'] for m in self.db_metrics.values())
            total_time = sum(m['total_time'] for m in self.db_metrics.values())
            
            return {
                'total_queries': total_queries,
                'total_time': total_time,
                'avg_time_per_query': total_time / total_queries if total_queries > 0 else 0,
                'operations': dict(self.db_metrics)
            }
    
    @classmethod
    def get_instance(cls) -> 'PerformanceMonitor':
        """获取监控器实例"""
        return cls() 