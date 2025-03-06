from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import UserViewSet

# 创建路由器
router = DefaultRouter()
router.register('', UserViewSet, basename='users')

# API URL配置
urlpatterns = [
    # 包含路由器生成的URL
    path('', include(router.urls)),
]

# 打印URL模式以进行调试
print("Available patterns:")
for pattern in router.urls:
    print(f"  {pattern.pattern}")
