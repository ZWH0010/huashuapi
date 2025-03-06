from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APITestCase, APIClient
from rest_framework import status
from django.utils import timezone
from datetime import timedelta
from .models import User
import logging
import uuid
from django.contrib.auth import authenticate
import json

logger = logging.getLogger(__name__)

class UserModelTests(TestCase):
    def setUp(self):
        """测试数据初始化"""
        self.user_data = {
            'name': '测试用户',
            'phone_number': '13800138000',
            'password': 'testpass123',  # 使用简单密码
            'start_date': timezone.now().date(),
            'end_date': (timezone.now() + timedelta(days=365)).date(),
            'is_active': True
        }
        # 创建用户并设置密码
        self.user = User.objects.create_user(**self.user_data)
        self.user.set_password(self.user_data['password'])
        self.user.save()

    def test_user_creation(self):
        """测试用户创建"""
        self.assertEqual(self.user.name, self.user_data['name'])
        self.assertEqual(self.user.phone_number, self.user_data['phone_number'])
        self.assertEqual(self.user.username, self.user_data['phone_number'])
        self.assertTrue(self.user.check_password(self.user_data['password']))

    def test_user_str_representation(self):
        """测试用户字符串表示"""
        expected_str = f"测试用户({self.user.phone_number})"
        self.assertEqual(str(self.user), expected_str)

    def test_user_validity(self):
        """测试用户有效期"""
        self.assertTrue(self.user.is_valid())
        
        # 测试过期用户
        self.user.end_date = timezone.now().date() - timezone.timedelta(days=1)
        self.user.save()
        self.assertFalse(self.user.is_valid())

class UserAPITests(TestCase):
    """用户API测试类"""
    
    def setUp(self):
        """测试前准备工作"""
        self.client = APIClient()
        self.user = User.objects.create(
            username='testuser',
            phone_number='13800138000',
            name='测试用户',
            start_date=timezone.now().date(),
            end_date=timezone.now().date() + timezone.timedelta(days=365),
            is_active=True
        )
        self.user.set_password('testpass123')
        self.user.save()
        
        # 测试用户数据
        self.user_data = {
            'name': '测试用户',
            'phone_number': '13826762968',
            'username': '13826762968',
            'password': 'testpass123',
            'confirm_password': 'testpass123',
            'start_date': '2025-03-05',
            'end_date': '2026-03-05',
            'is_active': True
        }
        
        logger.info(f"测试用户创建成功: {self.user.phone_number}")

    def test_user_registration(self):
        """测试用户注册"""
        url = reverse('users-list')
        logger.info(f"测试用户注册数据: {self.user_data}")
        response = self.client.post(url, self.user_data, format='json')
        logger.debug(f"注册响应内容: {response.content.decode('utf-8')}")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(User.objects.filter(phone_number='13826762968').exists())

    def test_user_login(self):
        """测试用户登录"""
        url = reverse('users-login')
        data = {
            'phone_number': '13800138000',
            'password': 'testpass123'
        }
        logger.info(f"测试登录请求数据: {data}")
        response = self.client.post(url, data, format='json')
        logger.debug(f"登录响应内容: {response.content.decode('utf-8')}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response_data = response.json()
        self.assertEqual(response_data['status'], 'success')
        self.assertIn('token', response_data['data'])
        self.assertIn('user', response_data['data'])

    def test_invalid_login(self):
        """测试无效登录"""
        url = reverse('users-login')
        # 错误密码
        data = {
            'phone_number': '13841440825',
            'password': 'wrongpass123'
        }
        logger.info(f"测试无效登录请求数据: {data}")
        response = self.client.post(url, data, format='json')
        logger.debug(f"无效登录响应内容: {response.content.decode('utf-8')}")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_change_password(self):
        """测试修改密码"""
        # 先登录
        self.client.force_authenticate(user=self.user)
        
        url = reverse('users-change-password', kwargs={'pk': self.user.pk})
        data = {
            'old_password': 'testpass123',
            'new_password': 'newpass123',
            'confirm_password': 'newpass123'
        }
        logger.info(f"测试修改密码请求数据: {data}")
        response = self.client.post(url, data, format='json')
        logger.debug(f"修改密码响应内容: {response.content.decode('utf-8')}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # 尝试用新密码登录
        self.client.force_authenticate(user=None)
        login_url = reverse('users-login')
        login_data = {
            'phone_number': '13800138000',
            'password': 'newpass123'
        }
        response = self.client.post(login_url, login_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_check_phone(self):
        """测试手机号检查"""
        url = reverse('users-check-phone')
        
        # 已存在的手机号
        data = {'phone_number': '13800138000'}
        logger.info(f"测试手机号检查请求数据: {data}")
        response = self.client.post(url, data, format='json')
        logger.debug(f"手机号检查响应内容: {response.content.decode('utf-8')}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()['exists'], True)
        
        # 不存在的手机号
        data = {'phone_number': '13700000000'}
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()['exists'], False) 