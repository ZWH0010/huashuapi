from django.core.cache import cache
from django.db.models import Count
from django.conf import settings
import logging
from typing import List, Dict, Any
from .models import Script
from .serializers import ScriptSerializer, ScriptBriefSerializer
from .cache import ScriptCacheManager

logger = logging.getLogger(__name__)

class ScriptCacheWarmupManager:
    """话术缓存预热管理器"""
    
    @classmethod
    def warmup_most_accessed_scripts(cls, limit: int = 100) -> None:
        """预热最常访问的话术"""
        try:
            # 获取最常访问的话术（这里假设有访问计数字段，如果没有可以根据其他条件筛选）
            scripts = Script.objects.order_by('-updated_at')[:limit]
            
            for script in scripts:
                serializer = ScriptSerializer(script)
                ScriptCacheManager.cache_script(script.id, serializer.data)
            
            logger.info(f"Successfully warmed up {len(scripts)} most accessed scripts")
        except Exception as e:
            logger.error(f"Error warming up most accessed scripts: {str(e)}")

    @classmethod
    def warmup_latest_scripts(cls, limit: int = 50) -> None:
        """预热最新的话术"""
        try:
            scripts = Script.objects.order_by('-created_at')[:limit]
            
            for script in scripts:
                serializer = ScriptSerializer(script)
                ScriptCacheManager.cache_script(script.id, serializer.data)
            
            logger.info(f"Successfully warmed up {len(scripts)} latest scripts")
        except Exception as e:
            logger.error(f"Error warming up latest scripts: {str(e)}")

    @classmethod
    def warmup_active_scripts(cls, limit: int = 200) -> None:
        """预热活跃的话术"""
        try:
            scripts = Script.objects.filter(is_active=True).order_by('-updated_at')[:limit]
            
            for script in scripts:
                serializer = ScriptSerializer(script)
                ScriptCacheManager.cache_script(script.id, serializer.data)
            
            logger.info(f"Successfully warmed up {len(scripts)} active scripts")
        except Exception as e:
            logger.error(f"Error warming up active scripts: {str(e)}")

    @classmethod
    def warmup_script_versions(cls, limit: int = 50) -> None:
        """预热话术版本列表"""
        try:
            # 获取最近更新的话术标题
            titles = Script.objects.values('title')\
                .annotate(version_count=Count('version'))\
                .filter(version_count__gt=1)\
                .order_by('-updated_at')[:limit]
            
            for title_obj in titles:
                title = title_obj['title']
                versions = Script.objects.filter(title=title).order_by('-version')
                serializer = ScriptBriefSerializer(versions, many=True)
                ScriptCacheManager.cache_script_versions(title, serializer.data)
            
            logger.info(f"Successfully warmed up versions for {len(titles)} scripts")
        except Exception as e:
            logger.error(f"Error warming up script versions: {str(e)}")

    @classmethod
    def warmup_all(cls) -> None:
        """执行所有预热操作"""
        try:
            logger.info("Starting cache warmup process...")
            
            cls.warmup_most_accessed_scripts()
            cls.warmup_latest_scripts()
            cls.warmup_active_scripts()
            cls.warmup_script_versions()
            
            logger.info("Cache warmup process completed successfully")
        except Exception as e:
            logger.error(f"Error during cache warmup process: {str(e)}")

    @classmethod
    def schedule_warmup(cls) -> None:
        """计划定时预热
        此方法可以在Django启动时调用，或者通过Celery等任务队列定时执行
        """
        try:
            from django.core.cache import cache
            
            # 检查是否已经在预热中，避免重复预热
            if not cache.add('script_cache_warming_up', True, timeout=3600):
                logger.info("Cache warmup is already in progress")
                return
            
            cls.warmup_all()
            
            # 预热完成后删除锁
            cache.delete('script_cache_warming_up')
            
        except Exception as e:
            logger.error(f"Error scheduling cache warmup: {str(e)}")
            # 确保删除锁
            cache.delete('script_cache_warming_up') 