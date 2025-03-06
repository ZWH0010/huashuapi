from django.shortcuts import redirect
from django.urls import resolve, reverse
from django.contrib import messages
import re
import logging

logger = logging.getLogger(__name__)

class AdminLoginRestrictionMiddleware:
    """
    限制普通用户登录管理系统的中间件
    """
    def __init__(self, get_response):
        self.get_response = get_response
        
    def __call__(self, request):
        # 检查是否是管理员页面的请求
        path = request.path_info.lstrip('/')
        
        # 记录请求路径，便于调试
        logger.debug(f"AdminLoginRestrictionMiddleware: 处理路径 {path}")
        
        if path.startswith('admin/'):
            # 如果是登录页面或登出页面，直接放行
            if re.match(r'^admin/login/?$', path) or re.match(r'^admin/logout/?$', path):
                logger.debug("AdminLoginRestrictionMiddleware: 允许访问登录/登出页面")
                return self.get_response(request)
                
            # 如果用户已登录但不是超级用户或工作人员
            if request.user.is_authenticated and not (request.user.is_superuser or request.user.is_staff):
                logger.warning(f"AdminLoginRestrictionMiddleware: 用户 {request.user.username} 尝试访问管理系统但没有权限")
                messages.error(request, '您没有权限访问管理系统')
                return redirect('admin:login')
                
        # 对于其他请求，正常处理
        return self.get_response(request) 