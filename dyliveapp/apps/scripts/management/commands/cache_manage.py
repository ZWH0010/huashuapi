from django.core.management.base import BaseCommand
from django.core.cache import cache
import logging
from apps.scripts.cache_warmup import ScriptCacheWarmupManager
from apps.scripts.cache_monitor import ScriptCacheMonitor
import json
from datetime import datetime

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = '缓存管理命令：预热和监控'

    def add_arguments(self, parser):
        parser.add_argument(
            '--action',
            choices=['warmup', 'stats', 'clear'],
            required=True,
            help='执行的操作：warmup(预热)、stats(统计)、clear(清除)'
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=100,
            help='预热时处理的记录数限制'
        )

    def handle(self, *args, **options):
        action = options['action']
        limit = options['limit']

        try:
            if action == 'warmup':
                self.warmup_cache(limit)
            elif action == 'stats':
                self.show_cache_stats()
            elif action == 'clear':
                self.clear_cache_stats()
        except Exception as e:
            self.stderr.write(self.style.ERROR(f'执行失败: {str(e)}'))
            logger.error(f"Cache management command failed: {str(e)}")

    def warmup_cache(self, limit):
        """执行缓存预热"""
        try:
            self.stdout.write(self.style.SUCCESS('开始缓存预热...'))
            
            # 预热最常访问的话术
            self.stdout.write('预热最常访问的话术...')
            ScriptCacheWarmupManager.warmup_most_accessed_scripts(limit)
            
            # 预热最新的话术
            self.stdout.write('预热最新的话术...')
            ScriptCacheWarmupManager.warmup_latest_scripts(limit // 2)
            
            # 预热活跃的话术
            self.stdout.write('预热活跃的话术...')
            ScriptCacheWarmupManager.warmup_active_scripts(limit * 2)
            
            # 预热话术版本列表
            self.stdout.write('预热话术版本列表...')
            ScriptCacheWarmupManager.warmup_script_versions(limit // 2)
            
            self.stdout.write(self.style.SUCCESS('缓存预热完成！'))
            
        except Exception as e:
            self.stderr.write(self.style.ERROR(f'缓存预热失败: {str(e)}'))
            logger.error(f"Cache warmup failed: {str(e)}")

    def show_cache_stats(self):
        """显示缓存统计信息"""
        try:
            stats = ScriptCacheMonitor.get_cache_stats()
            
            if not stats:
                self.stdout.write(self.style.WARNING('没有可用的缓存统计信息'))
                return
            
            # 显示总体指标
            self.stdout.write(self.style.SUCCESS('\n=== 总体指标 ==='))
            overall = stats.get('overall_metrics', {})
            self.stdout.write(f"总请求数: {overall.get('total', 0)}")
            self.stdout.write(f"命中数: {overall.get('hits', 0)}")
            self.stdout.write(f"未命中数: {overall.get('misses', 0)}")
            self.stdout.write(f"命中率: {overall.get('hit_rate', 0):.2%}")
            self.stdout.write(f"最后更新: {overall.get('last_update', 'N/A')}")
            
            # 显示各缓存键的命中率
            self.stdout.write(self.style.SUCCESS('\n=== 缓存键命中率 ==='))
            hit_rates = stats.get('hit_rates', {})
            for key, rate in hit_rates.items():
                self.stdout.write(f"{key}: {rate:.2%}")
            
            # 显示延迟统计
            self.stdout.write(self.style.SUCCESS('\n=== 延迟统计 (秒) ==='))
            latency = stats.get('latency', {})
            avg_latency = latency.get('average', {})
            details = latency.get('details', {})
            
            for key in avg_latency:
                self.stdout.write(f"\n{key}:")
                self.stdout.write(f"  平均: {avg_latency[key]:.4f}")
                if key in details:
                    detail = details[key]
                    self.stdout.write(f"  最小: {detail['min']:.4f}")
                    self.stdout.write(f"  最大: {detail['max']:.4f}")
                    self.stdout.write(f"  总数: {detail['count']}")
            
        except Exception as e:
            self.stderr.write(self.style.ERROR(f'获取缓存统计信息失败: {str(e)}'))
            logger.error(f"Error showing cache stats: {str(e)}")

    def clear_cache_stats(self):
        """清除缓存统计信息"""
        try:
            ScriptCacheMonitor.clear_metrics()
            self.stdout.write(self.style.SUCCESS('缓存统计信息已清除'))
        except Exception as e:
            self.stderr.write(self.style.ERROR(f'清除缓存统计信息失败: {str(e)}'))
            logger.error(f"Error clearing cache stats: {str(e)}") 