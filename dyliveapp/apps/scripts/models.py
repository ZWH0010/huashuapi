from django.db import models, transaction
from django.conf import settings
from apps.tags.models import Tag
from django.core.exceptions import ValidationError
from django.utils import timezone
import logging
from django.db.utils import IntegrityError
import threading
import time
from django.db.utils import OperationalError, DatabaseError
from django.db.models import Max

logger = logging.getLogger(__name__)

class Script(models.Model):
    """话术模型"""
    SCRIPT_TYPES = [
        ('opening', '开场白'),
        ('closing', '结束语'),
        ('qa', '问答'),
        ('custom', '自定义')
    ]
    
    title = models.CharField('标题', max_length=100, db_index=True)
    content = models.TextField('内容')
    script_type = models.CharField('类型', max_length=20, choices=SCRIPT_TYPES)
    version = models.IntegerField('版本号', default=1, db_index=True)
    is_active = models.BooleanField('是否启用', default=True)
    sort_order = models.IntegerField('排序', default=0)
    tags = models.ManyToManyField(
        'tags.Tag',
        through='ScriptTagRelation',
        through_fields=('script', 'tag'),
        related_name='scripts',
        verbose_name='标签'
    )
    
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)
    created_by = models.ForeignKey('users.User', on_delete=models.SET_NULL, null=True, related_name='created_scripts')
    updated_by = models.ForeignKey('users.User', on_delete=models.SET_NULL, null=True, related_name='updated_scripts')

    class Meta:
        verbose_name = '话术'
        verbose_name_plural = verbose_name
        ordering = ['-updated_at']
        indexes = [
            models.Index(fields=['title', 'version'], name='script_title_ver_idx'),
            models.Index(fields=['title', '-version'], name='script_title_latest_idx'),
        ]

    def __str__(self):
        return f"{self.title} (v{self.version})"

    def clean(self):
        """数据验证"""
        if not self.title:
            raise ValidationError({'title': ['标题不能为空']})
        if not self.content:
            raise ValidationError({'content': ['内容不能为空']})
        if self.script_type not in dict(self.SCRIPT_TYPES):
            raise ValidationError({'script_type': ['无效的话术类型']})
        if len(self.title) > 100:
            raise ValidationError({'title': ['标题长度不能超过100个字符']})

    def save(self, *args, **kwargs):
        """保存话术"""
        try:
            if not self.pk and not self.version:  # 只在新建且未指定version时设置为1
                self.version = 1
            self.clean()
            if not kwargs.get('update_fields') or 'updated_at' in kwargs.get('update_fields', []):
                self.updated_at = timezone.now()
            super().save(*args, **kwargs)
            logger.info(f"Script saved successfully: {self.title} (v{self.version})")
        except Exception as e:
            logger.error(f"Error saving script: {str(e)}")
            raise ValueError(f"保存话术失败: {str(e)}")

    def create_new_version(self, created_by=None):
        """创建话术新版本"""
        thread_name = threading.current_thread().name
        logger.info(f"[Thread {thread_name}] 开始创建新版本，当前话术：ID={self.id}, Title={self.title}, Version={self.version}")
        
        retry_count = 0
        max_retries = 3
        retry_delay = 1  # 初始重试延迟（秒）
        
        while retry_count < max_retries:
            try:
                # 使用 REPEATABLE READ 隔离级别
                with transaction.atomic():
                    # 使用 select_for_update(nowait=False) 获取行锁，设置等待
                    # 使用 title 和 version 的组合锁来确保版本号的唯一性
                    current_max_version = Script.objects.select_for_update(nowait=False)\
                        .filter(title=self.title)\
                        .aggregate(max_version=Max('version'))['max_version'] or 0
                        
                    logger.info(f"[Thread {thread_name}] 当前最大版本号：{current_max_version}")
                    
                    # 创建新版本记录
                    new_version_number = current_max_version + 1
                    logger.info(f"[Thread {thread_name}] 生成新版本号：{new_version_number}")
                    
                    # 创建新版本
                    new_script = Script.objects.create(
                        title=self.title,
                        version=new_version_number,
                        content=self.content,
                        script_type=self.script_type,
                        sort_order=self.sort_order,
                        is_active=self.is_active,
                        created_by=created_by or self.created_by
                    )
                    
                    logger.info(f"[Thread {thread_name}] 新版本创建成功：ID={new_script.id}, Title={new_script.title}, Version={new_script.version}")
                    
                    # 使用 bulk_create 优化标签关联创建
                    original_tags = list(self.tags.all().only('id'))
                    if original_tags:
                        relations = [
                            ScriptTagRelation(
                                script=new_script,
                                tag=tag,
                                created_by=created_by or self.created_by,
                                updated_by=created_by or self.created_by
                            ) for tag in original_tags
                        ]
                        ScriptTagRelation.objects.bulk_create(relations)
                        logger.info(f"[Thread {thread_name}] 批量创建标签关联完成，共 {len(relations)} 个")
                    
                    logger.info(f"[Thread {thread_name}] 新版本创建完成，版本号：{new_script.version}")
                    return new_script
                    
            except OperationalError as e:
                retry_count += 1
                if retry_count >= max_retries:
                    logger.error(f"[Thread {thread_name}] 创建新版本失败，已达到最大重试次数：{str(e)}")
                    raise
                
                # 使用指数退避策略
                wait_time = retry_delay * (2 ** (retry_count - 1))
                logger.warning(f"[Thread {thread_name}] 第 {retry_count} 次重试，等待 {wait_time} 秒后重试")
                time.sleep(wait_time)
                continue
                
            except Exception as e:
                logger.error(f"[Thread {thread_name}] 创建新版本时发生未知错误：{str(e)}")
                raise

class ScriptTagRelation(models.Model):
    """话术标签关联"""
    script = models.ForeignKey(
        Script,
        on_delete=models.CASCADE,
        related_name='script_tag_relations',
        verbose_name='话术'
    )
    tag = models.ForeignKey(
        'tags.Tag',
        on_delete=models.CASCADE,
        related_name='script_tag_relations',
        verbose_name='标签'
    )
    created_by = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_script_tag_relations',
        verbose_name='创建者'
    )
    updated_by = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        related_name='updated_script_tag_relations',
        verbose_name='更新者'
    )
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        verbose_name = '话术标签关联'
        verbose_name_plural = verbose_name
        unique_together = ('script', 'tag')
        ordering = ['-created_at']
        db_table = 'scripts_script_tags'  # 自定义表名，避免与自动生成的表名冲突

    def save(self, *args, **kwargs):
        """保存话术标签关联"""
        try:
            # 检查是否已存在相同的关联
            if not self.pk and ScriptTagRelation.objects.filter(script=self.script, tag=self.tag).exists():
                raise IntegrityError('标签关联已存在')
            
            # 验证标签是否启用
            if not self.tag.is_active:
                raise ValidationError({'tag': '不能关联未启用的标签'})

            # 更新时间
            self.updated_at = timezone.now()
            
            # 保存
            super().save(*args, **kwargs)
            logger.info(f"Script-Tag relation saved successfully: {self.script.title} - {self.tag.tag_name}")
            
        except IntegrityError as e:
            logger.error(f"Integrity error saving script-tag relation: {str(e)}")
            raise
        except ValidationError as e:
            logger.error(f"Validation error saving script-tag relation: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Error saving script-tag relation: {str(e)}")
            raise ValueError(f"保存话术标签关联失败: {str(e)}")

    def __str__(self):
        return f"{self.script.title} - {self.tag.tag_name}"

    def clean(self):
        """数据验证 - 优化查询"""
        if self.tag_id:
            # 使用select_related减少查询
            tag = Tag.objects.select_related().get(id=self.tag_id)
            if not tag.is_active:
                raise ValidationError({'tag': '不能关联未启用的标签'})