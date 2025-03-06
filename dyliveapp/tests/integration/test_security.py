import pytest
from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from apps.tags.models import Tag
from apps.scripts.models import Script
import jwt
from django.conf import settings

User = get_user_model()

class TestSecurity(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            phone_number='13800138000',
            password='testpass123'
        )
        self.other_user = User.objects.create_user(
            phone_number='13800138001',
            password='testpass123'
        )
        self.admin_user = User.objects.create_superuser(
            phone_number='13800138002',
            password='testpass123'
        )

    def test_jwt_token_security(self):
        """测试JWT Token安全性"""
        # 测试登录获取token
        response = self.client.post('/api/users/login/', {
            'phone_number': '13800138000',
            'password': 'testpass123'
        })
        assert response.status_code == 200
        token = response.data['token']

        # 验证token格式
        assert len(token.split('.')) == 3
        
        # 解码token验证payload
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=['HS256'])
        assert payload['phone_number'] == '13800138000'
        assert 'exp' in payload
        
        # 测试过期token
        expired_payload = {
            'phone_number': '13800138000',
            'exp': 1000000000  # 过期时间设置为过去
        }
        expired_token = jwt.encode(expired_payload, settings.SECRET_KEY, algorithm='HS256')
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {expired_token}')
        response = self.client.get('/api/users/profile/')
        assert response.status_code == 401

    def test_authorization(self):
        """测试授权控制"""
        # 创建测试数据
        self.client.force_authenticate(user=self.user)
        script_response = self.client.post('/api/scripts/', {
            'title': 'test_script',
            'content': 'test_content'
        })
        script_id = script_response.data['id']

        # 测试其他用户无法修改
        self.client.force_authenticate(user=self.other_user)
        response = self.client.patch(f'/api/scripts/{script_id}/', {
            'title': 'modified_title'
        })
        assert response.status_code == 403

        # 测试管理员可以修改
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.patch(f'/api/scripts/{script_id}/', {
            'title': 'admin_modified_title'
        })
        assert response.status_code == 200

    def test_input_validation(self):
        """测试输入验证和XSS防护"""
        self.client.force_authenticate(user=self.user)
        
        # 测试XSS注入
        xss_payload = '<script>alert("xss")</script>'
        response = self.client.post('/api/scripts/', {
            'title': xss_payload,
            'content': xss_payload
        })
        assert response.status_code == 201
        assert xss_payload not in response.data['title']
        assert xss_payload not in response.data['content']

        # 测试SQL注入
        sql_payload = "'; DROP TABLE scripts; --"
        response = self.client.post('/api/scripts/', {
            'title': sql_payload,
            'content': 'test_content'
        })
        assert response.status_code == 201
        assert Script.objects.filter(title=sql_payload).exists()

    def test_password_security(self):
        """测试密码安全性"""
        # 测试弱密码
        response = self.client.post('/api/users/', {
            'phone_number': '13800138003',
            'password': '123456'
        })
        assert response.status_code == 400

        # 测试强密码
        response = self.client.post('/api/users/', {
            'phone_number': '13800138003',
            'password': 'StrongPass123!'
        })
        assert response.status_code == 201 