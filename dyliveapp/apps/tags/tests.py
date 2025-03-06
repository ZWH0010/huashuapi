from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APITestCase, APIClient
from rest_framework import status
from django.utils import timezone
from django.db import transaction
from django.core.exceptions import ValidationError
from .models import Tag
from apps.users.models import User
import logging
import uuid

logger = logging.getLogger(__name__)

class TagModelTests(TestCase):
    def setUp(self):
        """测试数据初始化"""
        # 清理现有数据
        Tag.objects.all().delete()
        
        self.user = User.objects.create_user(
            name='测试用户',
            phone_number='13800138000',
            password='testpass123',
            start_date=timezone.now().date(),
            end_date=timezone.now().date() + timezone.timedelta(days=365)
        )
        
        self.tag_data = {
            'tag_name': '测试标签',
            'description': '这是一个测试标签',
            'created_by': self.user,
            'updated_by': self.user
        }
        self.tag = Tag.objects.create(**self.tag_data)

    def test_tag_creation(self):
        """测试标签创建"""
        self.assertEqual(self.tag.tag_name, self.tag_data['tag_name'])
        self.assertEqual(self.tag.description, self.tag_data['description'])
        self.assertTrue(self.tag.is_active)
        self.assertEqual(self.tag.sort_order, 0)

    def test_tag_str_representation(self):
        """测试标签字符串表示"""
        self.assertEqual(str(self.tag), self.tag_data['tag_name'])

    def test_tag_hierarchy(self):
        """测试标签层级关系"""
        # 创建子标签
        child_tag = Tag.objects.create(
            tag_name='子标签',
            parent=self.tag,
            created_by=self.user,
            updated_by=self.user
        )
        
        # 测试父子关系
        self.assertEqual(child_tag.parent, self.tag)
        self.assertIn(child_tag, self.tag.children.all())
        
        # 测试字符串表示
        self.assertEqual(str(child_tag), f"{self.tag.tag_name} > {child_tag.tag_name}")
        
        # 测试循环引用验证
        with self.assertRaises(ValidationError):
            self.tag.parent = child_tag
            self.tag.save()
            
        # 测试多级层级关系
        grandchild_tag = Tag.objects.create(
            tag_name='孙标签',
            parent=child_tag,
            created_by=self.user,
            updated_by=self.user
        )
        
        # 测试获取所有子标签
        children = self.tag.get_all_children(include_self=False)
        self.assertEqual(children.count(), 2)
        
        # 测试获取祖先标签
        ancestors = grandchild_tag.get_ancestors(include_self=False)
        self.assertEqual(len(ancestors), 2)
        self.assertEqual(ancestors[0], self.tag)
        self.assertEqual(ancestors[1], child_tag)

    def test_tag_validation(self):
        """测试标签验证"""
        # 测试空标签名
        with self.assertRaises(ValidationError):
            Tag.objects.create(
                tag_name='',
                created_by=self.user,
                updated_by=self.user
            )
        
        # 测试重复标签名
        with transaction.atomic():
            with self.assertRaises(ValidationError):
                try:
                    Tag.objects.create(
                        tag_name=self.tag_data['tag_name'],
                        created_by=self.user,
                        updated_by=self.user
                    )
                except ValueError as e:
                    if "Duplicate entry" in str(e):
                        raise ValidationError("标签名称已存在")
                    raise
        
        # 测试标签名去除空格
        tag = Tag.objects.create(
            tag_name='  测试标签2  ',
            created_by=self.user,
            updated_by=self.user
        )
        self.assertEqual(tag.tag_name, '测试标签2')

class TagAPITests(APITestCase):
    def setUp(self):
        """测试前的准备工作"""
        # 清理所有标签数据
        Tag.objects.all().delete()
        
        # 创建测试用户
        self.user = User.objects.create_user(
            name='测试用户',
            phone_number='13800138000',
            password='testpass123',
            start_date=timezone.now().date(),
            end_date=(timezone.now() + timezone.timedelta(days=365)).date()
        )
        self.admin_user = User.objects.create_user(
            name='管理员',
            phone_number='13800138001',
            password='adminpass123',
            is_staff=True,
            start_date=timezone.now().date(),
            end_date=(timezone.now() + timezone.timedelta(days=365)).date()
        )
        
        # 设置测试客户端
        self.client = APIClient()
        self.client.force_authenticate(user=self.admin_user)  # 使用管理员用户进行认证
        
        # 设置 URL
        self.list_url = reverse('tag-list')
        
        # 创建基础测试数据
        self.tag_data = {
            'tag_name': '测试标签',
            'description': '测试描述',
            'sort_order': 0
        }

    def test_create_tag(self):
        """测试创建标签"""
        self.client.force_authenticate(user=self.admin_user)
        url = reverse('tag-list')
        
        response = self.client.post(url, self.tag_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Tag.objects.count(), 1)
        self.assertEqual(Tag.objects.get().tag_name, self.tag_data['tag_name'])
        
        # 测试创建重复标签
        response = self.client.post(url, self.tag_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        
        # 测试创建空标签名
        invalid_data = self.tag_data.copy()
        invalid_data['tag_name'] = ''
        response = self.client.post(url, invalid_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_list_tags(self):
        """测试获取标签列表"""
        # 清理所有标签数据
        Tag.objects.all().delete()
        
        # 创建测试标签
        tag1 = Tag.objects.create(
            tag_name='标签1',
            created_by=self.admin_user,
            updated_by=self.admin_user
        )
        tag2 = Tag.objects.create(
            tag_name='标签2',
            created_by=self.admin_user,
            updated_by=self.admin_user
        )
        
        logger.info("已创建的测试标签:")
        logger.info(f"标签1: {tag1.id} - {tag1.tag_name}")
        logger.info(f"标签2: {tag2.id} - {tag2.tag_name}")
        
        # 获取标签列表
        response = self.client.get(self.list_url)
        logger.info("API 响应状态码: %s", response.status_code)
        logger.info("返回的数据类型: %s", type(response.data))
        logger.info("返回的原始数据: %s", response.data)
        
        # 验证响应状态和分页格式
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('count', response.data)
        self.assertIn('results', response.data)
        self.assertEqual(response.data['count'], 2)  # 总记录数应为2
        
        # 验证分页信息
        self.assertIsNone(response.data['next'])     # 没有下一页
        self.assertIsNone(response.data['previous']) # 没有上一页
        
        # 验证结果列表
        results = response.data['results']
        self.assertEqual(len(results), 2)  # 结果列表长度应为2
        
        # 验证返回的标签数据
        returned_tag_names = {tag['tag_name'] for tag in results}
        logger.info("返回的标签名称集合: %s", returned_tag_names)
        self.assertIn('标签1', returned_tag_names)
        self.assertIn('标签2', returned_tag_names)
        
        # 验证每个标签的字段
        for tag in results:
            logger.info("验证标签数据: %s", tag)
            self.assertIsInstance(tag, dict)  # 确保是字典类型
            self.assertIn('id', tag)
            self.assertIn('tag_name', tag)
            self.assertIn('usage_count', tag)
            self.assertEqual(tag['usage_count'], 0)  # 新创建的标签使用次数应为0

    def test_retrieve_tag(self):
        """测试获取单个标签"""
        tag = Tag.objects.create(
            tag_name='测试标签',
            created_by=self.admin_user,
            updated_by=self.admin_user
        )
        
        self.client.force_authenticate(user=self.user)
        url = reverse('tag-detail', args=[tag.id])
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['tag_name'], tag.tag_name)
        
        # 测试获取不存在的标签
        url = reverse('tag-detail', args=[99999])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_update_tag(self):
        """测试更新标签"""
        # 创建测试标签
        tag = Tag.objects.create(
            tag_name='原始标签',
            description='原始描述',
            created_by=self.admin_user,
            updated_by=self.admin_user
        )
        
        # 准备更新数据
        update_data = {
            'tag_name': '更新后的标签',
            'description': '更新后的描述',
            'sort_order': 1
        }
        
        # 测试普通用户无权更新
        self.client.force_authenticate(user=self.user)
        url = reverse('tag-detail', args=[tag.id])
        response = self.client.put(url, update_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        
        # 测试管理员可以更新
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.put(url, update_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # 验证更新结果
        tag.refresh_from_db()
        self.assertEqual(tag.tag_name, update_data['tag_name'])
        self.assertEqual(tag.description, update_data['description'])
        self.assertEqual(tag.sort_order, update_data['sort_order'])
        self.assertEqual(tag.updated_by, self.admin_user)
        
        # 测试更新不存在的标签
        url = reverse('tag-detail', args=[99999])
        response = self.client.put(url, update_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        
        # 测试更新为重复的标签名
        another_tag = Tag.objects.create(
            tag_name='另一个标签',
            created_by=self.admin_user,
            updated_by=self.admin_user
        )
        update_data['tag_name'] = another_tag.tag_name
        url = reverse('tag-detail', args=[tag.id])
        response = self.client.put(url, update_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_delete_tag(self):
        """测试删除标签"""
        # 创建父标签和子标签
        parent_tag = Tag.objects.create(
            tag_name='父标签',
            created_by=self.admin_user,
            updated_by=self.admin_user
        )
        child_tag = Tag.objects.create(
            tag_name='子标签',
            parent=parent_tag,
            created_by=self.admin_user,
            updated_by=self.admin_user
        )
        
        # 测试普通用户无权删除
        self.client.force_authenticate(user=self.user)
        url = reverse('tag-detail', args=[parent_tag.id])
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        
        # 测试管理员删除有子标签的父标签
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('无法删除存在子标签的标签', str(response.data))
        
        # 测试删除子标签
        url = reverse('tag-detail', args=[child_tag.id])
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Tag.objects.filter(id=child_tag.id).exists())
        
        # 现在可以删除父标签了
        url = reverse('tag-detail', args=[parent_tag.id])
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Tag.objects.filter(id=parent_tag.id).exists())
        
        # 测试删除不存在的标签
        url = reverse('tag-detail', args=[99999])
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_tag_tree(self):
        """测试获取标签树"""
        # 创建父标签
        parent_tag = Tag.objects.create(
            tag_name='父标签',
            created_by=self.admin_user,
            updated_by=self.admin_user
        )
        
        # 创建子标签
        child_tag = Tag.objects.create(
            tag_name='子标签',
            parent=parent_tag,
            created_by=self.admin_user,
            updated_by=self.admin_user
        )
        
        # 创建孙标签
        grandchild_tag = Tag.objects.create(
            tag_name='孙标签',
            parent=child_tag,
            created_by=self.admin_user,
            updated_by=self.admin_user
        )
        
        self.client.force_authenticate(user=self.user)
        url = reverse('tag-tree')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)  # 只有一个顶级标签
        self.assertEqual(len(response.data[0]['children']), 1)  # 有一个子标签
        self.assertEqual(len(response.data[0]['children'][0]['children']), 1)  # 有一个孙标签

    def test_activate_deactivate_tag(self):
        """测试标签激活和停用"""
        # 创建父标签和子标签
        parent_tag = Tag.objects.create(
            tag_name='父标签',
            created_by=self.admin_user,
            updated_by=self.admin_user
        )
        child_tag = Tag.objects.create(
            tag_name='子标签',
            parent=parent_tag,
            created_by=self.admin_user,
            updated_by=self.admin_user
        )
        
        # 测试普通用户无权停用标签
        self.client.force_authenticate(user=self.user)
        url = reverse('tag-deactivate', args=[parent_tag.id])
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        
        # 测试管理员停用父标签
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # 验证父标签和子标签都被停用
        parent_tag.refresh_from_db()
        child_tag.refresh_from_db()
        self.assertFalse(parent_tag.is_active)
        self.assertFalse(child_tag.is_active)
        
        # 测试激活子标签（应该失败，因为父标签是停用的）
        url = reverse('tag-activate', args=[child_tag.id])
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('父标签处于停用状态', str(response.data))
        
        # 先激活父标签
        url = reverse('tag-activate', args=[parent_tag.id])
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        parent_tag.refresh_from_db()
        self.assertTrue(parent_tag.is_active)
        
        # 再激活子标签
        url = reverse('tag-activate', args=[child_tag.id])
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        child_tag.refresh_from_db()
        self.assertTrue(child_tag.is_active)
        
        # 测试停用不存在的标签
        url = reverse('tag-deactivate', args=[99999])
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_tag_usage(self):
        """测试获取标签使用情况"""
        # 清理所有标签数据
        Tag.objects.all().delete()
        
        # 创建父子标签
        parent_tag = Tag.objects.create(
            tag_name='父标签',
            created_by=self.admin_user,
            updated_by=self.admin_user
        )
        child_tag = Tag.objects.create(
            tag_name='子标签',
            parent=parent_tag,
            created_by=self.admin_user,
            updated_by=self.admin_user
        )
        
        # 测试获取存在标签的使用情况
        url = reverse('tag-usage', args=[parent_tag.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['tag_name'], '父标签')
        self.assertEqual(response.data['usage_count'], 0)
        
        # 测试获取不存在标签的使用情况
        url = reverse('tag-usage', args=[99999])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_tag_sorting(self):
        """测试标签排序"""
        # 创建多个标签，设置不同的排序值
        tags_data = [
            {'tag_name': '标签A', 'sort_order': 3},
            {'tag_name': '标签B', 'sort_order': 1},
            {'tag_name': '标签C', 'sort_order': 2},
        ]
        
        created_tags = []
        for data in tags_data:
            tag = Tag.objects.create(
                tag_name=data['tag_name'],
                sort_order=data['sort_order'],
                created_by=self.admin_user,
                updated_by=self.admin_user
            )
            created_tags.append(tag)
        
        # 测试获取排序后的标签列表
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # 验证返回的标签是按sort_order升序排列的
        results = response.data['results']
        self.assertEqual(len(results), 3)
        self.assertEqual(results[0]['tag_name'], '标签B')  # sort_order: 1
        self.assertEqual(results[1]['tag_name'], '标签C')  # sort_order: 2
        self.assertEqual(results[2]['tag_name'], '标签A')  # sort_order: 3
        
        # 测试更新标签排序
        update_data = {'sort_order': 0}
        url = reverse('tag-detail', args=[created_tags[2].id])  # 更新标签C的排序
        response = self.client.patch(url, update_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # 验证更新后的排序
        response = self.client.get(self.list_url)
        results = response.data['results']
        self.assertEqual(results[0]['tag_name'], '标签C')  # sort_order: 0
        self.assertEqual(results[1]['tag_name'], '标签B')  # sort_order: 1
        self.assertEqual(results[2]['tag_name'], '标签A')  # sort_order: 3
        
        # 测试按名称排序
        url = f"{self.list_url}?ordering=tag_name"
        response = self.client.get(url)
        results = response.data['results']
        self.assertEqual(results[0]['tag_name'], '标签A')
        self.assertEqual(results[1]['tag_name'], '标签B')
        self.assertEqual(results[2]['tag_name'], '标签C')
        
        # 测试按名称倒序排序
        url = f"{self.list_url}?ordering=-tag_name"
        response = self.client.get(url)
        results = response.data['results']
        self.assertEqual(results[0]['tag_name'], '标签C')
        self.assertEqual(results[1]['tag_name'], '标签B')
        self.assertEqual(results[2]['tag_name'], '标签A') 