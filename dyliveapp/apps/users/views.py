from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser, AllowAny
from django_filters import rest_framework as filters
from django.contrib.auth.hashers import check_password, make_password
from django.utils import timezone
from rest_framework_simplejwt.tokens import RefreshToken
import logging
from django.core.cache import cache
from django.conf import settings
from django.db.models import Q
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from django.views.decorators.vary import vary_on_cookie
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle
import re
from django.contrib.auth import authenticate
import traceback

from .models import User
from .serializers import UserSerializer, UserLoginSerializer, UserBriefSerializer

# 配置日志
logger = logging.getLogger(__name__)

class UserFilter(filters.FilterSet):
    """用户过滤器"""
    name = filters.CharFilter(lookup_expr='icontains')
    phone_number = filters.CharFilter(lookup_expr='icontains')
    is_active = filters.BooleanFilter(method='filter_is_active')
    
    class Meta:
        model = User
        fields = ['name', 'phone_number', 'is_active']
        
    def filter_is_active(self, queryset, name, value):
        today = timezone.now().date()
        if value:  # 查询有效用户
            return queryset.filter(start_date__lte=today, end_date__gte=today)
        else:  # 查询无效用户
            return queryset.filter(end_date__lt=today)

class LoginRateThrottle(AnonRateThrottle):
    rate = '5/minute'
    scope = 'login'

class UserViewSet(viewsets.ModelViewSet):
    """
    用户视图集
    提供用户的增删改查功能
    """
    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]
    filterset_class = UserFilter
    search_fields = ['name', 'phone_number']
    ordering_fields = ['created_at', 'start_date', 'end_date']
    ordering = ['-created_at']

    def get_queryset(self):
        """优化查询集"""
        queryset = super().get_queryset()
        
        if self.action == 'list':
            # 列表查询时只返回必要字段，不使用 select_related
            return queryset.only(
                'id', 'name', 'phone_number', 'start_date', 'end_date'
            )
        elif self.action in ['retrieve', 'update', 'partial_update']:
            # 详情查询时，仅预加载更新用户关系
            return queryset.prefetch_related('updated_by')
        
        return queryset

    @method_decorator(cache_page(60))  # 缓存1分钟
    @method_decorator(vary_on_cookie)
    def list(self, request, *args, **kwargs):
        """列表查询添加缓存"""
        return super().list(request, *args, **kwargs)

    def get_permissions(self):
        """根据不同的操作设置不同的权限"""
        if self.action in ['login', 'check_phone', 'create']:
            return [AllowAny()]
        return [IsAuthenticated()]

    def get_serializer_class(self):
        """根据不同的操作返回不同的序列化器"""
        if self.action == 'login':
            return UserLoginSerializer
        elif self.action == 'list':
            return UserBriefSerializer
        return UserSerializer

    def perform_create(self, serializer):
        """创建用户时设置创建者"""
        if self.request.user.is_authenticated:
            serializer.save(created_by=self.request.user)
        else:
            serializer.save()

    def perform_update(self, serializer):
        """更新用户时设置更新者"""
        serializer.save(updated_by=self.request.user)

    @action(detail=False, methods=['post'], url_path='login')
    def login(self, request):
        """用户登录"""
        logger.info(f"开始处理登录请求: {request.data}")
        
        try:
            serializer = UserLoginSerializer(data=request.data)
            if not serializer.is_valid():
                logger.warning(f"数据验证失败: {serializer.errors}")
                return Response({
                    'status': 'error',
                    'message': serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # 获取验证后的用户
            user = serializer.validated_data['user']
            logger.info(f"用户验证成功: {user.phone_number}")

            # 生成令牌
            refresh = RefreshToken.for_user(user)
            
            return Response({
                'status': 'success',
                'data': {
                    'token': {
                        'refresh': str(refresh),
                        'access': str(refresh.access_token),
                    },
                    'user': {
                        'id': user.id,
                        'name': user.name,
                        'phone_number': user.phone_number,
                    }
                }
            })

        except Exception as e:
            logger.error(f"登录过程发生错误: {str(e)}")
            return Response({
                'status': 'error',
                'message': {
                    'non_field_errors': ['登录失败，请稍后重试']
                }
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['post'], url_path='check-phone')
    def check_phone(self, request):
        """检查手机号是否已注册"""
        phone_number = request.data.get('phone_number', '')
        exists = User.objects.filter(phone_number=phone_number).exists()
        return Response({'exists': exists})

    @action(detail=True, methods=['post'], url_path='change-password')
    def change_password(self, request, pk=None):
        """修改用户密码"""
        user = self.get_object()
        old_password = request.data.get('old_password')
        new_password = request.data.get('new_password')
        confirm_password = request.data.get('confirm_password')
        
        logger.info(f"测试修改密码请求数据: {request.data}")
        
        # 验证旧密码
        if not authenticate(username=user.phone_number, password=old_password):
            return Response({
                'status': 'error',
                'message': {'old_password': ['旧密码不正确']}
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # 验证新密码
        if new_password != confirm_password:
            return Response({
                'status': 'error',
                'message': {'confirm_password': ['两次输入的密码不一致']}
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # 设置新密码
        user.set_password(new_password)
        user.save()
        
        # 生成新令牌
        refresh = RefreshToken.for_user(user)
        
        logger.info(f"Password changed successfully for user: {user.name}")
        
        response_data = {
            'status': 'success',
            'message': '密码修改成功',
            'tokens': {
                'refresh': str(refresh),
                'access': str(refresh.access_token)
            }
        }
        
        logger.debug(f"修改密码响应内容: {response_data}")
        
        return Response(response_data)

    @action(detail=False)
    @method_decorator(cache_page(60))
    @method_decorator(vary_on_cookie)
    def profile(self, request):
        """获取用户资料（添加缓存）"""
        serializer = UserSerializer(request.user)
        return Response(serializer.data)
