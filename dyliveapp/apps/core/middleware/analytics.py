import time
from typing import Any, Callable
from django.http import HttpRequest, HttpResponse
from django.contrib.auth.models import AnonymousUser
from apps.core.monitoring.user_analytics import UserAnalytics

class UserAnalyticsMiddleware:
    """用户行为分析中间件"""

    def __init__(self, get_response: Callable) -> None:
        self.get_response = get_response
        self.analytics = UserAnalytics.get_instance()

    def __call__(self, request: HttpRequest) -> HttpResponse:
        # 开始计时
        start_time = time.time()

        # 获取用户ID
        user_id = None
        if hasattr(request, 'user') and not isinstance(request.user, AnonymousUser):
            user_id = request.user.id

        # 如果是已登录用户，记录会话开始
        if user_id:
            self.analytics.start_user_session(user_id)

        # 处理请求
        response = self.get_response(request)

        # 如果是已登录用户，记录行为
        if user_id:
            # 计算请求处理时间
            duration = time.time() - start_time

            # 准备上下文信息
            context = {
                'path': request.path,
                'method': request.method,
                'status_code': response.status_code,
                'duration': duration,
                'ip': self.get_client_ip(request),
                'user_agent': request.META.get('HTTP_USER_AGENT', ''),
            }

            # 构造行为描述
            action = f"{request.method}_{request.path.replace('/', '_')}"
            if len(action) > 100:  # 限制action长度
                action = action[:97] + "..."

            # 记录行为
            self.analytics.track_user_action(user_id, action, context)

            # 如果响应状态码表示会话结束，记录会话结束
            if response.status_code in [401, 403] or 'logout' in request.path.lower():
                self.analytics.end_user_session(user_id)

        return response

    def get_client_ip(self, request: HttpRequest) -> str:
        """获取客户端IP地址"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR', '') 