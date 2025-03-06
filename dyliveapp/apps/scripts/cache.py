from django.core.cache import cache
from django.conf import settings
import logging
import json
from typing import Optional, List, Dict, Any
from .cache_monitor import ScriptCacheMonitor

logger = logging.getLogger(__name__)

class ScriptCacheManager:
    """话术缓存管理器"""
    
    # 缓存键前缀
    SCRIPT_DETAIL_PREFIX = "script:detail:"
    SCRIPT_LIST_PREFIX = "script:list:"
    SCRIPT_VERSION_PREFIX = "script:versions:"
    SCRIPT_TAG_PREFIX = "script:tags:"
    
    # 缓存过期时间（秒）
    CACHE_TIMEOUT = 3600  # 1小时
    LIST_CACHE_TIMEOUT = 300  # 5分钟
    
    @classmethod
    def get_script_cache_key(cls, script_id: int) -> str:
        """获取话术详情缓存键"""
        return f"{cls.SCRIPT_DETAIL_PREFIX}{script_id}"
    
    @classmethod
    def get_script_list_cache_key(cls, params: Dict[str, Any]) -> str:
        """获取话术列表缓存键"""
        # 将查询参数排序，确保相同参数生成相同的缓存键
        sorted_params = sorted(params.items())
        params_str = json.dumps(sorted_params)
        return f"{cls.SCRIPT_LIST_PREFIX}{hash(params_str)}"
    
    @classmethod
    def get_script_versions_cache_key(cls, title: str) -> str:
        """获取话术版本列表缓存键"""
        return f"{cls.SCRIPT_VERSION_PREFIX}{title}"
    
    @classmethod
    def get_script_tags_cache_key(cls, script_id: int) -> str:
        """获取话术标签缓存键"""
        return f"{cls.SCRIPT_TAG_PREFIX}{script_id}"
    
    @classmethod
    @ScriptCacheMonitor.monitor_cache_operation('set', SCRIPT_DETAIL_PREFIX)
    def cache_script(cls, script_id: int, data: Dict) -> None:
        """缓存话术详情"""
        try:
            cache_key = cls.get_script_cache_key(script_id)
            cache.set(cache_key, data, cls.CACHE_TIMEOUT)
            logger.debug(f"Cached script detail: {cache_key}")
        except Exception as e:
            logger.error(f"Error caching script detail: {str(e)}")
    
    @classmethod
    @ScriptCacheMonitor.monitor_cache_operation('get', SCRIPT_DETAIL_PREFIX)
    def get_cached_script(cls, script_id: int) -> Optional[Dict]:
        """获取缓存的话术详情"""
        try:
            cache_key = cls.get_script_cache_key(script_id)
            data = cache.get(cache_key)
            if data:
                logger.debug(f"Cache hit for script detail: {cache_key}")
            return data
        except Exception as e:
            logger.error(f"Error getting cached script detail: {str(e)}")
            return None
    
    @classmethod
    @ScriptCacheMonitor.monitor_cache_operation('set', SCRIPT_LIST_PREFIX)
    def cache_script_list(cls, params: Dict[str, Any], data: List[Dict]) -> None:
        """缓存话术列表"""
        try:
            cache_key = cls.get_script_list_cache_key(params)
            cache.set(cache_key, data, cls.LIST_CACHE_TIMEOUT)
            logger.debug(f"Cached script list: {cache_key}")
        except Exception as e:
            logger.error(f"Error caching script list: {str(e)}")
    
    @classmethod
    @ScriptCacheMonitor.monitor_cache_operation('get', SCRIPT_LIST_PREFIX)
    def get_cached_script_list(cls, params: Dict[str, Any]) -> Optional[List[Dict]]:
        """获取缓存的话术列表"""
        try:
            cache_key = cls.get_script_list_cache_key(params)
            data = cache.get(cache_key)
            if data:
                logger.debug(f"Cache hit for script list: {cache_key}")
            return data
        except Exception as e:
            logger.error(f"Error getting cached script list: {str(e)}")
            return None
    
    @classmethod
    @ScriptCacheMonitor.monitor_cache_operation('set', SCRIPT_VERSION_PREFIX)
    def cache_script_versions(cls, title: str, versions: List[Dict]) -> None:
        """缓存话术版本列表"""
        try:
            cache_key = cls.get_script_versions_cache_key(title)
            cache.set(cache_key, versions, cls.CACHE_TIMEOUT)
            logger.debug(f"Cached script versions: {cache_key}")
        except Exception as e:
            logger.error(f"Error caching script versions: {str(e)}")
    
    @classmethod
    @ScriptCacheMonitor.monitor_cache_operation('get', SCRIPT_VERSION_PREFIX)
    def get_cached_script_versions(cls, title: str) -> Optional[List[Dict]]:
        """获取缓存的话术版本列表"""
        try:
            cache_key = cls.get_script_versions_cache_key(title)
            data = cache.get(cache_key)
            if data:
                logger.debug(f"Cache hit for script versions: {cache_key}")
            return data
        except Exception as e:
            logger.error(f"Error getting cached script versions: {str(e)}")
            return None
    
    @classmethod
    @ScriptCacheMonitor.monitor_cache_operation('set', SCRIPT_TAG_PREFIX)
    def cache_script_tags(cls, script_id: int, tags: List[Dict]) -> None:
        """缓存话术标签"""
        try:
            cache_key = cls.get_script_tags_cache_key(script_id)
            cache.set(cache_key, tags, cls.CACHE_TIMEOUT)
            logger.debug(f"Cached script tags: {cache_key}")
        except Exception as e:
            logger.error(f"Error caching script tags: {str(e)}")
    
    @classmethod
    @ScriptCacheMonitor.monitor_cache_operation('get', SCRIPT_TAG_PREFIX)
    def get_cached_script_tags(cls, script_id: int) -> Optional[List[Dict]]:
        """获取缓存的话术标签"""
        try:
            cache_key = cls.get_script_tags_cache_key(script_id)
            data = cache.get(cache_key)
            if data:
                logger.debug(f"Cache hit for script tags: {cache_key}")
            return data
        except Exception as e:
            logger.error(f"Error getting cached script tags: {str(e)}")
            return None
    
    @classmethod
    def invalidate_script_cache(cls, script_id: int) -> None:
        """使话术缓存失效"""
        try:
            # 删除话术详情缓存
            cache_key = cls.get_script_cache_key(script_id)
            cache.delete(cache_key)
            
            # 删除相关的标签缓存
            tags_cache_key = cls.get_script_tags_cache_key(script_id)
            cache.delete(tags_cache_key)
            
            logger.debug(f"Invalidated script cache: {script_id}")
        except Exception as e:
            logger.error(f"Error invalidating script cache: {str(e)}")
    
    @classmethod
    def invalidate_script_list_cache(cls) -> None:
        """使话术列表缓存失效"""
        try:
            # 使用通配符删除所有列表缓存
            cache.delete_pattern(f"{cls.SCRIPT_LIST_PREFIX}*")
            logger.debug("Invalidated all script list caches")
        except Exception as e:
            logger.error(f"Error invalidating script list cache: {str(e)}")
    
    @classmethod
    def invalidate_script_versions_cache(cls, title: str) -> None:
        """使话术版本列表缓存失效"""
        try:
            cache_key = cls.get_script_versions_cache_key(title)
            cache.delete(cache_key)
            logger.debug(f"Invalidated script versions cache: {title}")
        except Exception as e:
            logger.error(f"Error invalidating script versions cache: {str(e)}") 