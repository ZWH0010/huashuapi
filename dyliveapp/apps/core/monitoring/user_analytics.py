import logging
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
import threading
from collections import defaultdict
import json
from django.core.cache import cache
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models import Count, Avg, Max, Min

logger = logging.getLogger(__name__)

class UserAnalytics:
    """用户行为分析器"""
    
    _instance = None
    _lock = threading.Lock()
    
    # 缓存键
    USER_ACTIVITY_KEY = "user_analytics:activity"
    USER_STATS_KEY = "user_analytics:stats"
    
    # 默认保留时间（天）
    DEFAULT_RETENTION_DAYS = 30
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialize()
        return cls._instance
    
    def _initialize(self):
        """初始化分析器"""
        self.user_activity = defaultdict(lambda: {
            'session_count': 0,
            'last_active': None,
            'total_duration': 0,
            'actions': defaultdict(int)
        })
        self.load_from_cache()
    
    def track_user_action(self, user_id: int, action: str, context: Dict[str, Any] = None) -> None:
        """追踪用户行为"""
        try:
            timestamp = datetime.now()
            
            with self._lock:
                if user_id not in self.user_activity:
                    self.user_activity[user_id] = {
                        'session_count': 0,
                        'last_active': None,
                        'total_duration': 0,
                        'actions': defaultdict(int)
                    }
                
                activity = self.user_activity[user_id]
                activity['last_active'] = timestamp
                activity['actions'][action] += 1
                
                # 保存到缓存
                self.save_to_cache()
                
                # 记录到日志
                logger.info(
                    f"User action tracked - User ID: {user_id}, Action: {action}",
                    extra={
                        'user_id': user_id,
                        'action': action,
                        'context': context
                    }
                )
                
        except Exception as e:
            logger.error(f"Error tracking user action: {str(e)}")
    
    def start_user_session(self, user_id: int) -> None:
        """开始用户会话"""
        try:
            with self._lock:
                if user_id not in self.user_activity:
                    self.user_activity[user_id] = {
                        'session_count': 0,
                        'last_active': None,
                        'total_duration': 0,
                        'actions': defaultdict(int)
                    }
                
                activity = self.user_activity[user_id]
                activity['session_count'] += 1
                activity['last_active'] = datetime.now()
                
                # 保存到缓存
                self.save_to_cache()
                
        except Exception as e:
            logger.error(f"Error starting user session: {str(e)}")
    
    def end_user_session(self, user_id: int) -> None:
        """结束用户会话"""
        try:
            with self._lock:
                if user_id in self.user_activity:
                    activity = self.user_activity[user_id]
                    if activity['last_active']:
                        duration = (datetime.now() - activity['last_active']).total_seconds()
                        activity['total_duration'] += duration
                        activity['last_active'] = None
                        
                        # 保存到缓存
                        self.save_to_cache()
                
        except Exception as e:
            logger.error(f"Error ending user session: {str(e)}")
    
    def get_user_stats(self, user_id: int) -> Dict[str, Any]:
        """获取用户统计信息"""
        with self._lock:
            if user_id not in self.user_activity:
                return {}
            
            activity = self.user_activity[user_id]
            return {
                'session_count': activity['session_count'],
                'last_active': activity['last_active'].isoformat() if activity['last_active'] else None,
                'total_duration': activity['total_duration'],
                'action_counts': dict(activity['actions'])
            }
    
    def get_most_active_users(self, limit: int = 10) -> List[Dict[str, Any]]:
        """获取最活跃用户"""
        with self._lock:
            # 按会话数排序
            users = sorted(
                self.user_activity.items(),
                key=lambda x: x[1]['session_count'],
                reverse=True
            )[:limit]
            
            return [
                {
                    'user_id': user_id,
                    'session_count': activity['session_count'],
                    'last_active': activity['last_active'].isoformat() if activity['last_active'] else None,
                    'total_duration': activity['total_duration'],
                    'action_counts': dict(activity['actions'])
                }
                for user_id, activity in users
            ]
    
    def get_popular_actions(self) -> Dict[str, int]:
        """获取最受欢迎的操作"""
        with self._lock:
            action_counts = defaultdict(int)
            for activity in self.user_activity.values():
                for action, count in activity['actions'].items():
                    action_counts[action] += count
            
            return dict(sorted(
                action_counts.items(),
                key=lambda x: x[1],
                reverse=True
            ))
    
    def get_activity_summary(self) -> Dict[str, Any]:
        """获取活动摘要"""
        with self._lock:
            total_sessions = sum(a['session_count'] for a in self.user_activity.values())
            total_actions = sum(
                sum(actions.values())
                for a in self.user_activity.values()
                for actions in [a['actions']]
            )
            
            return {
                'total_users': len(self.user_activity),
                'total_sessions': total_sessions,
                'total_actions': total_actions,
                'avg_sessions_per_user': total_sessions / len(self.user_activity) if self.user_activity else 0,
                'avg_actions_per_session': total_actions / total_sessions if total_sessions > 0 else 0,
                'popular_actions': self.get_popular_actions()
            }
    
    def save_to_cache(self) -> None:
        """保存数据到缓存"""
        try:
            # 序列化数据
            cache_data = {
                str(user_id): {
                    'session_count': activity['session_count'],
                    'last_active': activity['last_active'].isoformat() if activity['last_active'] else None,
                    'total_duration': activity['total_duration'],
                    'actions': dict(activity['actions'])
                }
                for user_id, activity in self.user_activity.items()
            }
            
            # 保存到缓存
            cache.set(self.USER_ACTIVITY_KEY, json.dumps(cache_data), timeout=None)
            
        except Exception as e:
            logger.error(f"Error saving to cache: {str(e)}")
    
    def load_from_cache(self) -> None:
        """从缓存加载数据"""
        try:
            cache_data = cache.get(self.USER_ACTIVITY_KEY)
            if not cache_data:
                return
            
            data = json.loads(cache_data)
            
            with self._lock:
                for user_id, activity in data.items():
                    self.user_activity[int(user_id)] = {
                        'session_count': activity['session_count'],
                        'last_active': datetime.fromisoformat(activity['last_active']) if activity['last_active'] else None,
                        'total_duration': activity['total_duration'],
                        'actions': defaultdict(int, activity['actions'])
                    }
                    
        except Exception as e:
            logger.error(f"Error loading from cache: {str(e)}")
    
    def clear_old_data(self, days: int = None) -> None:
        """清除旧数据"""
        if days is None:
            days = self.DEFAULT_RETENTION_DAYS
        
        cutoff_date = datetime.now() - timedelta(days=days)
        
        with self._lock:
            for user_id in list(self.user_activity.keys()):
                activity = self.user_activity[user_id]
                if activity['last_active'] and activity['last_active'] < cutoff_date:
                    del self.user_activity[user_id]
            
            # 保存到缓存
            self.save_to_cache()
    
    def get_user_segments(self) -> Dict[str, List[int]]:
        """获取用户分群"""
        with self._lock:
            segments = {
                'power_users': [],    # 高频活跃用户
                'regular_users': [],  # 普通用户
                'inactive_users': [], # 不活跃用户
                'new_users': []       # 新用户
            }
            
            now = datetime.now()
            for user_id, activity in self.user_activity.items():
                if not activity['last_active']:
                    continue
                
                days_since_last_active = (now - activity['last_active']).days
                session_count = activity['session_count']
                action_count = sum(activity['actions'].values())
                
                if days_since_last_active <= 7 and session_count >= 10:
                    segments['power_users'].append(user_id)
                elif days_since_last_active <= 30 and session_count >= 5:
                    segments['regular_users'].append(user_id)
                elif days_since_last_active > 30:
                    segments['inactive_users'].append(user_id)
                elif session_count < 5:
                    segments['new_users'].append(user_id)
            
            return segments
    
    @classmethod
    def get_instance(cls) -> 'UserAnalytics':
        """获取分析器实例"""
        return cls() 