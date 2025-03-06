from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ScriptViewSet

# 创建路由器
router = DefaultRouter()
router.register(r'scripts', ScriptViewSet)

# URL patterns
urlpatterns = [
    path('', include(router.urls)),
]
