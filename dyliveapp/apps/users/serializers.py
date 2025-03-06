from rest_framework import serializers
from django.contrib.auth.hashers import make_password
from django.utils import timezone
from django.core.validators import RegexValidator
import logging
from .models import User
import re
from django.contrib.auth import authenticate

logger = logging.getLogger(__name__)

class UserSerializer(serializers.ModelSerializer):
    """用户序列化器"""
    password = serializers.CharField(
        write_only=True,
        required=True,
        style={'input_type': 'password'},
        min_length=6,
        max_length=128,
        error_messages={
            'min_length': '密码长度不能少于6个字符',
            'max_length': '密码长度不能超过128个字符',
            'required': '请输入密码',
            'blank': '密码不能为空'
        }
    )
    confirm_password = serializers.CharField(
        write_only=True,
        required=True,
        style={'input_type': 'password'},
        error_messages={
            'required': '请确认密码',
            'blank': '确认密码不能为空'
        }
    )
    is_active = serializers.SerializerMethodField()
    phone_number = serializers.CharField(
        validators=[
            RegexValidator(
                regex=r'^1[3-9]\d{9}$',
                message='请输入有效的11位手机号'
            )
        ],
        error_messages={
            'required': '请输入手机号',
            'blank': '手机号不能为空'
        }
    )
    username = serializers.CharField(required=False)

    class Meta:
        model = User
        fields = [
            'id', 'username', 'name', 'phone_number', 'password', 'confirm_password',
            'start_date', 'end_date', 'created_at', 'updated_at', 'is_active'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_is_active(self, obj):
        """获取用户是否在有效期内"""
        return obj.is_valid()

    def validate_phone_number(self, value):
        """验证手机号"""
        try:
            # 检查手机号是否已存在
            if self.instance is None:  # 创建新用户时
                if User.objects.filter(phone_number=value).exists():
                    raise serializers.ValidationError("该手机号已被注册")
            else:  # 更新用户时
                if User.objects.filter(phone_number=value).exclude(id=self.instance.id).exists():
                    raise serializers.ValidationError("该手机号已被注册")
            return value
        except Exception as e:
            logger.error(f"Phone number validation error: {str(e)}")
            raise

    def validate(self, data):
        """验证数据"""
        try:
            # 验证密码
            if 'password' in data and 'confirm_password' in data:
                if data['password'] != data['confirm_password']:
                    raise serializers.ValidationError({"confirm_password": "两次输入的密码不一致"})
            
            # 验证日期
            if 'start_date' in data and 'end_date' in data:
                if data['start_date'] > data['end_date']:
                    raise serializers.ValidationError({"end_date": "结束日期不能早于开始日期"})
                
                # 如果是更新操作，且更新了日期，检查是否会影响现有用户
                if self.instance and self.instance.is_valid():
                    today = timezone.now().date()
                    if data['end_date'] < today:
                        raise serializers.ValidationError({"end_date": "不能将有效期结束日期设置为过去的日期"})
            
            return data
        except serializers.ValidationError:
            raise
        except Exception as e:
            logger.error(f"Data validation error: {str(e)}")
            raise serializers.ValidationError("数据验证失败")

    def create(self, validated_data):
        """创建用户"""
        try:
            validated_data.pop('confirm_password', None)
            password = validated_data.pop('password')
            
            # 如果用户提供了username，则移除它，让UserManager处理
            validated_data.pop('username', None)
            
            # 创建用户实例
            user = User.objects.create_user(
                password=password,
                **validated_data
            )
            
            logger.info(f"User created successfully: {user.name}")
            return user
        except Exception as e:
            logger.error(f"User creation error: {str(e)}")
            raise serializers.ValidationError("用户创建失败")

    def update(self, instance, validated_data):
        """更新用户"""
        try:
            validated_data.pop('confirm_password', None)
            
            # 如果提供了新密码，则更新密码
            if 'password' in validated_data:
                password = validated_data.pop('password')
                instance.set_password(password)
            
            # 更新其他字段
            for attr, value in validated_data.items():
                setattr(instance, attr, value)
            
            instance.save()
            logger.info(f"User updated successfully: {instance.name}")
            return instance
        except Exception as e:
            logger.error(f"User update error: {str(e)}")
            raise serializers.ValidationError("用户更新失败")

class UserLoginSerializer(serializers.Serializer):
    """用户登录序列化器"""
    phone_number = serializers.CharField(
        required=True,
        error_messages={
            'required': '请输入手机号',
            'blank': '手机号不能为空'
        }
    )
    password = serializers.CharField(
        required=True,
        write_only=True,
        error_messages={
            'required': '请输入密码',
            'blank': '密码不能为空'
        }
    )

    def validate_phone_number(self, value):
        """验证手机号格式"""
        logger.debug(f"验证手机号: {value}")
        
        if not value:
            logger.warning("手机号为空")
            raise serializers.ValidationError('手机号不能为空')
            
        if not re.match(r'^1[3-9]\d{9}$', value):
            logger.warning(f"手机号格式无效: {value}")
            raise serializers.ValidationError('请输入有效的11位手机号')
            
        # 检查用户是否存在
        try:
            user = User.objects.get(phone_number=value)
            logger.debug(f"找到用户: {user.phone_number}")
        except User.DoesNotExist:
            logger.warning(f"用户不存在: {value}")
            raise serializers.ValidationError('用户不存在')
            
        return value

    def validate(self, attrs):
        """验证用户凭据"""
        logger.debug("开始验证用户凭据")
        
        try:
            phone_number = attrs.get('phone_number')
            password = attrs.get('password')
            
            logger.debug(f"尝试认证用户: {phone_number}")
            
            # 使用 authenticate 进行认证
            user = authenticate(
                username=phone_number,
                password=password
            )
            
            if not user:
                logger.warning(f"认证失败: {phone_number}")
                raise serializers.ValidationError({
                    'non_field_errors': ['手机号或密码错误']
                })

            if not user.is_active:
                logger.warning(f"用户已禁用: {phone_number}")
                raise serializers.ValidationError({
                    'non_field_errors': ['该账号已被禁用']
                })

            if not user.is_valid():
                logger.warning(f"账号已过期: {phone_number}")
                raise serializers.ValidationError({
                    'non_field_errors': ['账号已过期']
                })

            logger.info(f"用户认证成功: {phone_number}")
            attrs['user'] = user
            return attrs

        except serializers.ValidationError:
            raise
        except Exception as e:
            logger.error(f"验证过程发生错误: {str(e)}")
            raise serializers.ValidationError({
                'non_field_errors': ['登录验证失败']
            })

    class Meta:
        ref_name = 'UserLogin'  # 为 API 文档提供引用名称

class UserBriefSerializer(serializers.ModelSerializer):
    """用户简要信息序列化器（用于列表展示）"""
    is_active = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'name', 'phone_number', 'is_active']

    def get_is_active(self, obj):
        return obj.is_valid()
