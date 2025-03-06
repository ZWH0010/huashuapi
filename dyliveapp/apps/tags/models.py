from django.db import models, transaction
from django.core.exceptions import ValidationError
import logging
from django.db.models import Q
from django.db.models import Count
from django.db.models import OuterRef
from django.db.models import Subquery
from django.db.models import Case
from django.db.models import When
from django.db.models import Value
from django.db.models import CharField
from django.db.models import F
from django.db.models import Prefetch

logger = logging.getLogger(__name__)

class Tag(models.Model):
    """话术标签模型"""
    tag_name = models.CharField(
        '标签名称', 
        max_length=50, 
        unique=True,
        help_text='标签的名称，必须唯一',
        error_messages={
            'unique': '该标签名称已存在',
        }
    )
    description = models.TextField(
        '标签描述',
        blank=True,
        help_text='标签的详细描述'
    )
    is_active = models.BooleanField(
        '是否启用',
        default=True,
        help_text='标签是否可用'
    )
    sort_order = models.IntegerField(
        '排序',
        default=0,
        help_text='标签的排序权重，数字越大越靠前'
    )
    parent = models.ForeignKey(
        'self',
        verbose_name='父标签',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='children',
        help_text='父标签，用于构建标签层级关系'
    )
    created_by = models.ForeignKey(
        'users.User',
        verbose_name='创建者',
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_tags',
        help_text='创建该标签的用户'
    )
    updated_by = models.ForeignKey(
        'users.User',
        verbose_name='更新者',
        on_delete=models.SET_NULL,
        null=True,
        related_name='updated_tags',
        help_text='最后更新该标签的用户'
    )
    created_at = models.DateTimeField(
        '创建时间', 
        auto_now_add=True,
        help_text='标签创建的时间'
    )
    updated_at = models.DateTimeField(
        '更新时间', 
        auto_now=True,
        help_text='标签最后更新的时间'
    )

    class Meta:
        verbose_name = '话术标签'
        verbose_name_plural = verbose_name
        ordering = ['-sort_order', 'tag_name']
        indexes = [
            models.Index(fields=['tag_name'], name='tag_name_idx'),
            models.Index(fields=['sort_order'], name='sort_order_idx'),
            models.Index(fields=['is_active'], name='is_active_idx'),
        ]
        permissions = [
            ("can_manage_tags", "Can manage tags"),
            ("can_view_inactive_tags", "Can view inactive tags"),
        ]

    def __str__(self):
        """返回标签的字符串表示"""
        if self.parent:
            return f"{self.parent.tag_name} > {self.tag_name}"
        return self.tag_name

    def clean(self):
        """
        模型验证
        """
        errors = {}
        
        # 验证标签名称
        if not self.tag_name or not self.tag_name.strip():
            errors['tag_name'] = '标签名称不能为空'
        
        # 验证父标签关系
        if self.parent:
            # 检查父标签是否存在
            if not Tag.objects.filter(id=self.parent.id).exists():
                errors['parent'] = '父标签不存在'
            
            # 检查是否形成循环引用
            if self.pk:
                if self.parent.pk == self.pk:
                    errors['parent'] = '标签不能将自己设为父标签'
                
                # 检查是否将一个子标签设为父标签
                children_pks = set(self.get_all_children().values_list('pk', flat=True))
                if self.parent.pk in children_pks:
                    errors['parent'] = '不能将子标签设为父标签'
            
            # 检查父标签是否已启用
            if not self.parent.is_active:
                errors['parent'] = '不能选择未启用的标签作为父标签'

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        """
        保存标签时的处理
        """
        try:
            # 标签名称去除首尾空格
            if self.tag_name:
                self.tag_name = self.tag_name.strip()
            
            # 数据验证
            self.clean()
            
            # 保存标签
            super().save(*args, **kwargs)
            logger.info(f"Tag saved successfully: {self.tag_name}")
            
        except ValidationError as e:
            logger.warning(f"Validation error when saving tag {self.tag_name}: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Error saving tag {self.tag_name}: {str(e)}")
            raise ValueError(f"保存标签失败: {str(e)}")

    def get_all_children(self, include_self=False):
        """
        获取所有子标签，使用递归查询优化性能
        
        Args:
            include_self: 是否包含自己
            
        Returns:
            QuerySet: 包含所有子标签的查询集
        """
        queryset = Tag.objects.none()
        if include_self:
            queryset = Tag.objects.filter(pk=self.pk)
        
        # 使用递归CTE查询获取所有子标签
        children = Tag.objects.raw("""
            WITH RECURSIVE tag_tree AS (
                SELECT * FROM tags_tag WHERE parent_id = %s
                UNION ALL
                SELECT t.* FROM tags_tag t
                INNER JOIN tag_tree tt ON t.parent_id = tt.id
            )
            SELECT * FROM tag_tree
        """, [self.pk])
        
        return queryset | Tag.objects.filter(pk__in=[child.pk for child in children])

    def get_ancestors(self, include_self=False):
        """
        获取所有祖先标签，使用递归查询优化性能
        
        Args:
            include_self: 是否包含自己
            
        Returns:
            list: 包含所有祖先标签的列表，从顶级标签开始
        """
        ancestors = []
        if include_self:
            ancestors.append(self)
        
        # 使用递归CTE查询获取所有祖先标签
        ancestors_query = Tag.objects.raw("""
            WITH RECURSIVE tag_tree AS (
                SELECT * FROM tags_tag WHERE id = %s
                UNION ALL
                SELECT t.* FROM tags_tag t
                INNER JOIN tag_tree tt ON t.id = tt.parent_id
            )
            SELECT * FROM tag_tree WHERE id != %s
            ORDER BY created_at DESC
        """, [self.parent_id if self.parent_id else 0, self.pk])
        
        ancestors.extend(list(ancestors_query))
        return list(reversed(ancestors))

    def get_siblings(self, include_self=False):
        """
        获取同级标签
        
        Args:
            include_self: 是否包含自己
            
        Returns:
            QuerySet: 包含所有同级标签的查询集
        """
        queryset = Tag.objects.filter(parent=self.parent)
        if not include_self:
            queryset = queryset.exclude(pk=self.pk)
        return queryset.order_by('-sort_order', 'tag_name')

    def deactivate(self):
        """
        停用标签及其所有子标签，使用事务确保原子性
        """
        try:
            with transaction.atomic():
                self.is_active = False
                self.save()
                
                # 停用所有子标签
                children = self.get_all_children()
                children.update(is_active=False)
                
                logger.info(f"Tag {self.tag_name} and its children have been deactivated")
        except Exception as e:
            logger.error(f"Error deactivating tag {self.tag_name}: {str(e)}")
            raise ValueError(f"停用标签失败: {str(e)}")

    def activate(self):
        """
        启用标签，同时确保父标签也被启用
        """
        try:
            with transaction.atomic():
                # 如果有父标签且未启用，则先启用父标签
                if self.parent and not self.parent.is_active:
                    self.parent.activate()
                
                self.is_active = True
                self.save()
                logger.info(f"Tag {self.tag_name} has been activated")
        except Exception as e:
            logger.error(f"Error activating tag {self.tag_name}: {str(e)}")
            raise ValueError(f"启用标签失败: {str(e)}")