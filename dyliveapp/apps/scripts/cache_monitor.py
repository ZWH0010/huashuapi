from django.core.cache import cache
from django.conf import settings
import logging
import time
from typing import Dict, Any
from collections import defaultdict
import json
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class ScriptCacheMonitor:
    """话术缓存监控管理器"""
    
    # 监控指标的缓存键
    METRICS_KEY = "script:cache:metrics"
    HITS_KEY = "script:cache:hits"
    MISSES_KEY = "script:cache:misses"
    LATENCY_KEY = "script:cache:latency"
    
    # 监控数据保留时间（秒）
    METRICS_RETENTION = 86400  # 24小时
    
    @classmethod
    def record_cache_hit(cls, cache_key: str, latency: float) -> None:
        """记录缓存命中"""
        try:
            # 更新命中计数
            hits = cache.get(cls.HITS_KEY, {})
            hits[cache_key] = hits.get(cache_key, 0) + 1
            cache.set(cls.HITS_KEY, hits, cls.METRICS_RETENTION)
            
            # 更新延迟统计
            cls._update_latency_stats(cache_key, latency)
            
            # 更新总体指标
            cls._update_metrics('hits')
            
        except Exception as e:
            logger.error(f"Error recording cache hit: {str(e)}")
    
    @classmethod
    def record_cache_miss(cls, cache_key: str, latency: float) -> None:
        """记录缓存未命中"""
        try:
            # 更新未命中计数
            misses = cache.get(cls.MISSES_KEY, {})
            misses[cache_key] = misses.get(cache_key, 0) + 1
            cache.set(cls.MISSES_KEY, misses, cls.METRICS_RETENTION)
            
            # 更新延迟统计
            cls._update_latency_stats(cache_key, latency)
            
            # 更新总体指标
            cls._update_metrics('misses')
            
        except Exception as e:
            logger.error(f"Error recording cache miss: {str(e)}")
    
    @classmethod
    def _update_latency_stats(cls, cache_key: str, latency: float) -> None:
        """更新延迟统计"""
        try:
            stats = cache.get(cls.LATENCY_KEY, {})
            if cache_key not in stats:
                stats[cache_key] = {
                    'min': latency,
                    'max': latency,
                    'sum': latency,
                    'count': 1
                }
            else:
                current = stats[cache_key]
                current['min'] = min(current['min'], latency)
                current['max'] = max(current['max'], latency)
                current['sum'] += latency
                current['count'] += 1
                stats[cache_key] = current
            
            cache.set(cls.LATENCY_KEY, stats, cls.METRICS_RETENTION)
            
        except Exception as e:
            logger.error(f"Error updating latency stats: {str(e)}")
    
    @classmethod
    def _update_metrics(cls, metric_type: str) -> None:
        """更新总体指标"""
        try:
            metrics = cache.get(cls.METRICS_KEY, {
                'hits': 0,
                'misses': 0,
                'total': 0,
                'hit_rate': 0.0,
                'last_update': None
            })
            
            metrics[metric_type] = metrics.get(metric_type, 0) + 1
            metrics['total'] = metrics['hits'] + metrics['misses']
            metrics['hit_rate'] = metrics['hits'] / metrics['total'] if metrics['total'] > 0 else 0
            metrics['last_update'] = datetime.now().isoformat()
            
            cache.set(cls.METRICS_KEY, metrics, cls.METRICS_RETENTION)
            
        except Exception as e:
            logger.error(f"Error updating metrics: {str(e)}")
    
    @classmethod
    def get_cache_stats(cls) -> Dict[str, Any]:
        """获取缓存统计信息"""
        try:
            metrics = cache.get(cls.METRICS_KEY, {})
            hits = cache.get(cls.HITS_KEY, {})
            misses = cache.get(cls.MISSES_KEY, {})
            latency = cache.get(cls.LATENCY_KEY, {})
            
            # 计算每个缓存键的命中率
            hit_rates = {}
            for key in set(hits.keys()) | set(misses.keys()):
                total = hits.get(key, 0) + misses.get(key, 0)
                hit_rates[key] = hits.get(key, 0) / total if total > 0 else 0
            
            # 计算平均延迟
            avg_latency = {}
            for key, stats in latency.items():
                avg_latency[key] = stats['sum'] / stats['count'] if stats['count'] > 0 else 0
            
            return {
                'overall_metrics': metrics,
                'hit_rates': hit_rates,
                'latency': {
                    'average': avg_latency,
                    'details': latency
                }
            }
            
        except Exception as e:
            logger.error(f"Error getting cache stats: {str(e)}")
            return {}
    
    @classmethod
    def clear_metrics(cls) -> None:
        """清除所有监控指标"""
        try:
            cache.delete(cls.METRICS_KEY)
            cache.delete(cls.HITS_KEY)
            cache.delete(cls.MISSES_KEY)
            cache.delete(cls.LATENCY_KEY)
            logger.info("Successfully cleared all cache metrics")
        except Exception as e:
            logger.error(f"Error clearing cache metrics: {str(e)}")
    
    @classmethod
    def monitor_cache_operation(cls, operation_type: str, cache_key: str):
        """缓存操作监控装饰器"""
        def decorator(func):
            def wrapper(*args, **kwargs):
                start_time = time.time()
                result = func(*args, **kwargs)
                latency = time.time() - start_time
                
                if operation_type == 'get':
                    if result is not None:
                        cls.record_cache_hit(cache_key, latency)
                    else:
                        cls.record_cache_miss(cache_key, latency)
                
                return result
            return wrapper
        return decorator 