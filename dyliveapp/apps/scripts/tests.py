from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APITestCase, APIClient
from rest_framework import status
from django.utils import timezone
from datetime import timedelta
from django.core.exceptions import ValidationError
from .models import Script, ScriptTagRelation
from apps.tags.models import Tag
from apps.users.models import User
import logging
import uuid
import io
import csv
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db.utils import IntegrityError
from django.test.utils import override_settings
from unittest.mock import patch

logger = logging.getLogger(__name__)

# 测试数据常量
TEST_DATA = {
    'SCRIPT_TYPES': ['opening', 'closing', 'qa', 'custom'],
    'TITLE_MAX_LENGTH': 100,
    'CONTENT_MAX_LENGTH': 10000,
    'VALID_SCRIPT': {
        'title': '测试话术',
        'content': '这是测试话术内容',
        'script_type': 'custom'
    },
    'INVALID_SCRIPT': {
        'title': '',
        'content': '',
        'script_type': 'invalid'
    }
}

class BaseTestCase:
    """基础测试类，提供通用的测试工具方法"""
    
    @classmethod
    def setUpTestData(cls):
        """设置测试数据"""
        logger.info("Setting up test data...")

    def setUp(self):
        """每个测试方法执行前的设置"""
        logger.info(f"Starting test: {self._testMethodName}")

    def tearDown(self):
        """每个测试方法执行后的清理"""
        logger.info(f"Finished test: {self._testMethodName}")
    
    def create_user(self, is_admin=False, **kwargs):
        """创建测试用户"""
        try:
            phone = kwargs.pop('phone_number', f"138{str(uuid.uuid4().int)[:8]}")
            user_data = {
                'phone_number': phone,
                'password': 'testpass123',
                'name': '测试用户',
                'start_date': timezone.now().date(),
                'end_date': (timezone.now() + timedelta(days=365)).date(),
                'is_staff': is_admin,
                'is_superuser': is_admin
            }
            user_data.update(kwargs)
            user = User.objects.create_user(**user_data)
            logger.info(f"Created test user: {user.name} ({user.phone_number})")
            return user
        except Exception as e:
            logger.error(f"Error creating test user: {str(e)}")
            raise

    def create_tag(self, **kwargs):
        """创建测试标签"""
        try:
            tag_data = {
                'tag_name': f'测试标签_{uuid.uuid4().hex[:6]}',
                'created_by': self.admin_user,
                'updated_by': self.admin_user
            }
            tag_data.update(kwargs)
            tag = Tag.objects.create(**tag_data)
            logger.info(f"Created test tag: {tag.tag_name}")
            return tag
        except Exception as e:
            logger.error(f"Error creating test tag: {str(e)}")
            raise

    def create_script(self, **kwargs):
        """创建测试话术"""
        try:
            script_data = TEST_DATA['VALID_SCRIPT'].copy()
            script_data.update({
                'title': f"{script_data['title']}_{uuid.uuid4().hex[:6]}",
                'created_by': self.admin_user,
                'updated_by': self.admin_user
            })
            script_data.update(kwargs)
            script = Script.objects.create(**script_data)
            logger.info(f"Created test script: {script.title}")
            return script
        except Exception as e:
            logger.error(f"Error creating test script: {str(e)}")
            raise

    def create_script_with_tags(self, tag_count=2):
        """创建带有标签的测试话术"""
        try:
            script = self.create_script()
            tags = [self.create_tag() for _ in range(tag_count)]
            for tag in tags:
                ScriptTagRelation.objects.create(
                    script=script,
                    tag=tag,
                    created_by=self.admin_user,
                    updated_by=self.admin_user
                )
            logger.info(f"Created script with {tag_count} tags")
            return script, tags
        except Exception as e:
            logger.error(f"Error creating script with tags: {str(e)}")
            raise

class ScriptModelTests(TestCase, BaseTestCase):
    """话术模型测试"""
    
    def setUp(self):
        """测试数据初始化"""
        super().setUp()
        self.admin_user = self.create_user(is_admin=True)
        self.user = self.create_user()
        self.script = self.create_script()
        self.tag = self.create_tag()

    def test_script_creation(self):
        """测试话术创建"""
        self.assertEqual(self.script.title.startswith(TEST_DATA['VALID_SCRIPT']['title']), True)
        self.assertEqual(self.script.script_type, TEST_DATA['VALID_SCRIPT']['script_type'])
        self.assertTrue(self.script.is_active)
        self.assertEqual(self.script.version, 1)

    def test_script_str_representation(self):
        """测试话术字符串表示"""
        expected_str = f"{self.script.title} (v{self.script.version})"
        self.assertEqual(str(self.script), expected_str)

    def test_script_validation(self):
        """测试话术验证"""
        # 测试创建没有标题的话术
        with self.assertRaises(ValueError) as context:
            self.create_script(title='')
        self.assertIn('标题不能为空', str(context.exception))

        # 测试创建没有内容的话术
        with self.assertRaises(ValueError) as context:
            self.create_script(content='')
        self.assertIn('内容不能为空', str(context.exception))

        # 测试创建无效类型的话术
        with self.assertRaises(ValueError) as context:
            self.create_script(script_type='invalid_type')
        self.assertIn('无效的话术类型', str(context.exception))

        # 测试创建标题过长的话术
        with self.assertRaises(ValueError) as context:
            self.create_script(title='a' * 101)  # 101个字符
        self.assertIn('标题长度不能超过100个字符', str(context.exception))

        # 测试正常创建话术
        script = self.create_script()
        self.assertIsNotNone(script)
        self.assertEqual(script.version, 1)

    def test_script_tag_relation(self):
        """测试话术标签关联"""
        script, tags = self.create_script_with_tags()
        self.assertEqual(script.tags.count(), 2)
        
        # 测试标签关联的唯一性
        with self.assertRaises(IntegrityError):
            ScriptTagRelation.objects.create(
                script=script,
                tag=tags[0],
                created_by=self.admin_user,
                updated_by=self.admin_user
            )

        # 测试关联已停用的标签
        inactive_tag = self.create_tag(is_active=False)
        with self.assertRaises(ValidationError):
            ScriptTagRelation.objects.create(
                script=script,
                tag=inactive_tag,
                created_by=self.admin_user,
                updated_by=self.admin_user
            )

    def test_create_new_version(self):
        """测试创建新版本"""
        script, tags = self.create_script_with_tags()
        new_version = script.create_new_version(self.admin_user)
        
        self.assertEqual(new_version.version, script.version + 1)
        self.assertEqual(new_version.title, script.title)
        self.assertEqual(new_version.content, script.content)
        self.assertEqual(new_version.tags.count(), script.tags.count())

        # 测试版本号递增
        another_version = new_version.create_new_version(self.admin_user)
        self.assertEqual(another_version.version, new_version.version + 1)

class ScriptAPITests(APITestCase, BaseTestCase):
    """话术API测试"""
    
    def setUp(self):
        """测试数据初始化"""
        super().setUp()
        self.client = APIClient()
        self.admin_user = self.create_user(is_admin=True)
        self.user = self.create_user()
        self.script, self.tags = self.create_script_with_tags()

    @override_settings(REST_FRAMEWORK={'DEFAULT_AUTHENTICATION_CLASSES': []})
    def test_authentication_required(self):
        """测试认证要求"""
        urls = [
            reverse('script-list'),
            reverse('script-detail', args=[self.script.id]),
            reverse('script-new-version', args=[self.script.id]),
            reverse('script-versions', args=[self.script.id]),
            reverse('script-bulk-delete'),
            reverse('script-bulk-update-status'),
        ]
        
        for url in urls:
            response = self.client.get(url)
            self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_list_scripts(self):
        """测试获取话术列表"""
        url = reverse('script-list')
        
        # 未登录用户
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        
        # 普通用户
        self.client.force_authenticate(user=self.user)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreater(len(response.data), 0)

        # 测试分页
        for _ in range(15):  # 创建超过一页的数据
            self.create_script()
        response = self.client.get(url)
        self.assertIn('count', response.data)
        self.assertIn('next', response.data)
        self.assertIn('results', response.data)

        # 测试过滤和搜索
        response = self.client.get(f"{url}?search={self.script.title}")
        self.assertEqual(len(response.data['results']), 1)

    def test_create_script(self):
        """测试创建话术"""
        # 未认证用户
        data = {
            'title': '测试话术',
            'content': '测试内容',
            'script_type': 'custom'
        }
        response = self.client.post('/api/scripts/', data)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        # 普通用户
        self.client.force_authenticate(user=self.user)
        response = self.client.post('/api/scripts/', data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['title'], '测试话术')

        # 无效数据
        response = self.client.post('/api/scripts/', {})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_update_script(self):
        """测试更新话术"""
        url = reverse('script-detail', args=[self.script.id])
        data = {
            'title': '更新后的话术',
            'content': '这是更新后的内容',
            'tag_ids': [self.tags[0].id]
        }
        
        # 管理员可以更新
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.patch(url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['title'], data['title'])
        self.assertEqual(len(response.data['tags']), 1)

        # 测试更新不存在的话术
        invalid_url = reverse('script-detail', args=[99999])
        response = self.client.patch(invalid_url, data)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        # 测试并发更新
        with patch('django.utils.timezone.now') as mock_now:
            mock_now.return_value = timezone.now() + timedelta(seconds=1)
            concurrent_data = {'title': '并发更新'}
            response = self.client.patch(url, concurrent_data)
            self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_script_versions(self):
        """测试话术版本管理"""
        self.client.force_authenticate(user=self.admin_user)
        
        # 创建初始话术
        script = self.create_script(title="测试话术")
        self.assertEqual(script.version, 1)
        
        # 创建新版本
        url = reverse('script-new-version', kwargs={'pk': script.pk})
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['version'], 2)
        
        # 再次创建新版本
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['version'], 3)
        
        # 验证版本列表
        url = reverse('script-versions', kwargs={'pk': script.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 3)
        versions = [item['version'] for item in response.data]
        self.assertEqual(sorted(versions), [1, 2, 3])
        
        # 验证原始话术仍然存在
        self.assertTrue(Script.objects.filter(pk=script.pk).exists())
        
        # 测试并发创建新版本
        from concurrent.futures import ThreadPoolExecutor
        import threading
        
        def create_version():
            client = APIClient()
            client.force_authenticate(user=self.admin_user)
            url = reverse('script-new-version', kwargs={'pk': script.pk})
            return client.post(url)
        
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(create_version) for _ in range(3)]
            responses = [f.result() for f in futures]
        
        # 确保原始话术仍然存在
        self.assertTrue(Script.objects.filter(pk=script.pk).exists())
        
        # 确保所有响应都是成功的
        for response in responses:
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)
            
        versions = [r.data['version'] for r in responses]
        self.assertEqual(len(set(versions)), 3)  # 确保版本号没有重复
        self.assertTrue(all(v > 3 for v in versions))  # 确保版本号都大于3

    def test_search_functionality(self):
        """测试搜索功能"""
        # 创建测试数据
        self.create_script_with_tags()
        self.create_script_with_tags()
        
        # 创建一些带特定标签的测试话术
        tag1 = self.create_tag(tag_name='标签1')
        tag2 = self.create_tag(tag_name='标签2')
        script1 = self.create_script(title='测试话术1')
        script2 = self.create_script(title='测试话术2')
        script3 = self.create_script(title='特殊话术')

        # 认证用户
        self.client.force_authenticate(user=self.admin_user)

        # 测试关键词搜索
        response = self.client.get('/api/scripts/search/', {'keyword': '测试'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 4)  # 包括带标签的测试话术

        # 测试标签搜索
        response = self.client.get('/api/scripts/search/', {'tag_ids': f'{tag1.id},{tag2.id}'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 0)

        # 测试组合搜索
        response = self.client.get('/api/scripts/search/', {
            'keyword': '测试',
            'tag_ids': f'{tag1.id},{tag2.id}'
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 0)

    def test_bulk_operations(self):
        """测试批量操作"""
        # 创建测试数据
        self.client.force_authenticate(user=self.admin_user)  # 添加认证
        script = self.create_script_with_tags()
        scripts = [
            self.create_script(),
            self.create_script(),
            self.create_script()
        ]
        script_ids = [s.id for s in scripts]

        # 测试批量删除
        url = reverse('script-bulk-delete')
        response = self.client.post(url, {'script_ids': script_ids}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['delete_count'], len(script_ids))

        # 验证删除结果
        for script_id in script_ids:
            self.assertFalse(Script.objects.filter(id=script_id).exists())

    def test_import_export(self):
        """测试导入导出功能"""
        self.client.force_authenticate(user=self.admin_user)
        
        # 创建测试标签
        tag1 = self.create_tag(tag_name='标签1')
        tag2 = self.create_tag(tag_name='标签2')
        
        # 测试正常导入
        csv_content = "标题,内容,话术类型\n测试导入,导入的内容,custom"
        csv_file = SimpleUploadedFile(
            "scripts.csv",
            csv_content.encode('utf-8'),
            content_type="text/csv"
        )
        
        url = reverse('script-import-scripts')
        response = self.client.post(
            url,
            {
                'file': csv_file,
                'tag_ids': [tag1.id, tag2.id]
            },
            format='multipart'
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['created_count'], 1)
        self.assertTrue(response.data['success'])

        # 测试导入无效数据
        invalid_csv_content = "标题,内容,话术类型\n,,custom"
        invalid_csv_file = SimpleUploadedFile(
            "invalid_scripts.csv",
            invalid_csv_content.encode('utf-8'),
            content_type="text/csv"
        )
        
        response = self.client.post(url, {'file': invalid_csv_file}, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_207_MULTI_STATUS)
        self.assertEqual(response.data['created_count'], 0)
        self.assertFalse(response.data['success'])
        self.assertTrue('errors' in response.data)

        # 测试文件格式错误
        txt_file = SimpleUploadedFile(
            "scripts.txt",
            b"invalid content",
            content_type="text/plain"
        )
        response = self.client.post(url, {'file': txt_file}, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue('error' in response.data)

    def test_export_scripts(self):
        """测试导出话术功能"""
        self.client.force_authenticate(user=self.admin_user)
        
        # 创建一些测试数据
        scripts = [self.create_script_with_tags() for _ in range(3)]
        
        # 测试导出
        url = reverse('script-export-scripts')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response['Content-Type'], 'text/csv')
        self.assertTrue(response['Content-Disposition'].startswith('attachment'))
        
        # 验证导出的内容
        content = response.content.decode('utf-8')
        csv_reader = csv.reader(io.StringIO(content))
        rows = list(csv_reader)
        
        # 验证标题行
        self.assertEqual(rows[0], ['标题', '内容', '话术类型', '标签'])
        # 验证数据行数
        self.assertGreater(len(rows), 1)

    def test_bulk_update_status(self):
        """测试批量更新话术状态"""
        self.client.force_authenticate(user=self.admin_user)
        
        # 创建测试数据
        scripts = [self.create_script() for _ in range(3)]
        script_ids = [s.id for s in scripts]
        
        # 测试批量停用
        url = reverse('script-bulk-update-status')
        response = self.client.post(url, {
            'ids': script_ids,
            'is_active': False
        }, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['updated_count'], len(script_ids))
        
        # 验证更新结果
        for script_id in script_ids:
            script = Script.objects.get(id=script_id)
            self.assertFalse(script.is_active)
        
        # 测试批量启用
        response = self.client.post(url, {
            'ids': script_ids,
            'is_active': True
        }, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['updated_count'], len(script_ids))
        
        # 验证更新结果
        for script_id in script_ids:
            script = Script.objects.get(id=script_id)
            self.assertTrue(script.is_active)

    def test_search_by_tags(self):
        """测试按标签组合搜索话术"""
        self.client.force_authenticate(user=self.admin_user)
        
        # 创建测试数据
        script = self.create_script()
        tags = [self.create_tag() for _ in range(3)]
        for tag in tags:
            ScriptTagRelation.objects.create(
                script=script,
                tag=tag,
                created_by=self.admin_user,
                updated_by=self.admin_user
            )
        
        # 测试单个标签搜索
        url = reverse('script-search-by-tags')
        response = self.client.get(f"{url}?tag_ids[]={tags[0].id}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['data']), 1)
        
        # 测试多个标签组合搜索
        tag_ids = [str(tag.id) for tag in tags[:2]]
        response = self.client.get(f"{url}?{'&'.join(f'tag_ids[]={id}' for id in tag_ids)}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['data']), 1)
        
        # 测试无效标签ID
        response = self.client.get(f"{url}?tag_ids[]=99999")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['data']), 0)

    def test_error_handling(self):
        """测试错误处理"""
        self.client.force_authenticate(user=self.admin_user)
        
        # 测试创建无效话术
        url = reverse('script-list')
        invalid_data = {
            'title': 'a' * 101,  # 超过最大长度
            'content': '',  # 空内容
            'script_type': 'invalid_type'  # 无效类型
        }
        response = self.client.post(url, invalid_data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue('title' in response.data or 'content' in response.data or 'script_type' in response.data)
        
        # 测试更新不存在的话术
        url = reverse('script-detail', args=[99999])
        response = self.client.patch(url, {'title': '新标题'})
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        
        # 测试批量操作空列表
        url = reverse('script-bulk-delete')
        response = self.client.post(url, {'script_ids': []})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        
        # 测试导入空文件
        url = reverse('script-import-scripts')
        empty_file = SimpleUploadedFile("empty.csv", b"", content_type="text/csv")
        response = self.client.post(url, {'file': empty_file})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST) 