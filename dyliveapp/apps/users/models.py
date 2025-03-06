from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.contrib.auth.hashers import make_password
from django.contrib.auth.password_validation import validate_password
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

def validate_phone_number(phone_number: str) -> None:
    """
    验证手机号格式
    
    Args:
        phone_number: 待验证的手机号
        
    Raises:
        ValidationError: 当手机号格式不正确时抛出
    """
    phone_validator = RegexValidator(
        regex=r'^1[3-9]\d{9}$',
        message='请输入有效的11位手机号'
    )
    try:
        phone_validator(phone_number)
    except ValidationError as e:
        logger.error(f"Invalid phone number format: {phone_number}")
        raise ValidationError({'phone_number': str(e)})

def normalize_phone_number(phone_number: str) -> str:
    """
    规范化手机号（去除空格和其他字符）
    
    Args:
        phone_number: 原始手机号
        
    Returns:
        str: 规范化后的手机号
    """
    return ''.join(filter(str.isdigit, str(phone_number)))

class UserManager(BaseUserManager):
    """自定义用户管理器"""
    
    def _create_user(self, phone_number, password=None, **extra_fields):
        if not phone_number:
            raise ValueError('手机号必须提供')
        
        user = self.model(phone_number=phone_number,username = phone_number, **extra_fields)
        if password:
            # 直接使用 set_password，避免触发 password 属性
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_user(self, phone_number, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', False)
        extra_fields.setdefault('is_superuser', False)
        return self._create_user(phone_number, password, **extra_fields)

    def create_superuser(self, phone_number, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        return self._create_user(phone_number, password, **extra_fields)

class User(AbstractUser):
    """用户模型"""
    #username = None  # 不禁用 username 字段
    phone_number = models.CharField(
        '手机号',
        max_length=11,
        unique=True,
        validators=[
            RegexValidator(
                regex=r'^1[3-9]\d{9}$',
                message='请输入有效的11位手机号'
            )
        ],
        help_text='用户手机号，用于登录'
    )
    name = models.CharField('姓名', max_length=50, help_text='用户姓名')
    start_date = models.DateField('有效期开始日期', help_text='账号有效期开始日期')
    end_date = models.DateField('有效期结束日期', help_text='账号有效期结束日期')
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True, help_text='用户最后更新时间')
    created_by = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_users',
        verbose_name='创建用户',
        help_text='创建该用户的管理员'
    )
    updated_by = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        related_name='updated_users',
        verbose_name='更新用户',
        help_text='最后更新该用户的管理员'
    )

    objects = UserManager()

    USERNAME_FIELD = 'phone_number'
    REQUIRED_FIELDS = ['name', 'start_date', 'end_date']

    class Meta:
        verbose_name = '前端用户'
        verbose_name_plural = '前端用户'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name}({self.phone_number})"

    def is_valid(self):
        """检查用户是否在有效期内"""
        today = timezone.now().date()
        return (
            self.is_active and 
            self.start_date <= today <= self.end_date
        )

    # 移除所有自定义的密码相关属性和方法，使用父类的实现
