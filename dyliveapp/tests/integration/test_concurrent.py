import pytest
import threading
import random
import string
from django.test import TestCase
from django.contrib.auth import get_user_model
from apps.tags.models import Tag
from apps.scripts.models import Script
from rest_framework.test import APIClient
from django.db import transaction

User = get_user_model()

def random_string(length=10):
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

class TestConcurrentOperations(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            phone_number='13800138000',
            password='testpass123'
        )
        self.client.force_authenticate(user=self.user)
        self.lock = threading.Lock()
        self.errors = []

    def test_concurrent_tag_creation(self):
        """测试并发创建标签"""
        def create_tag():
            try:
                with transaction.atomic():
                    response = self.client.post('/api/tags/', {
                        'name': f'test_tag_{random_string()}'
                    })
                    assert response.status_code in [201, 400]
            except Exception as e:
                with self.lock:
                    self.errors.append(str(e))

        threads = []
        for _ in range(10):
            t = threading.Thread(target=create_tag)
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        assert len(self.errors) == 0
        assert Tag.objects.count() > 0

    def test_concurrent_script_creation(self):
        """测试并发创建话术"""
        tag = Tag.objects.create(name='test_tag')

        def create_script():
            try:
                with transaction.atomic():
                    response = self.client.post('/api/scripts/', {
                        'title': f'test_script_{random_string()}',
                        'content': f'content_{random_string()}',
                        'tags': [tag.id]
                    })
                    assert response.status_code in [201, 400]
            except Exception as e:
                with self.lock:
                    self.errors.append(str(e))

        threads = []
        for _ in range(10):
            t = threading.Thread(target=create_script)
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        assert len(self.errors) == 0
        assert Script.objects.count() > 0

    def test_concurrent_script_version(self):
        """测试并发创建话术版本"""
        script = Script.objects.create(
            title='test_script',
            content='test_content',
            created_by=self.user
        )

        def create_version():
            try:
                with transaction.atomic():
                    response = self.client.post(
                        f'/api/scripts/{script.id}/new_version/',
                        {
                            'content': f'content_{random_string()}'
                        }
                    )
                    assert response.status_code in [201, 400]
            except Exception as e:
                with self.lock:
                    self.errors.append(str(e))

        threads = []
        for _ in range(10):
            t = threading.Thread(target=create_version)
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        assert len(self.errors) == 0
        script.refresh_from_db()
        assert Script.objects.filter(title=script.title).count() > 1 