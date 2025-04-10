from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import TagViewSet

# 创建路由器
router = DefaultRouter()
router.register(r'tags', TagViewSet)

# URL patterns
urlpatterns = [
    path('', include(router.urls)),
]
