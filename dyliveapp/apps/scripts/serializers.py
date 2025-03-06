from rest_framework import serializers
from .models import Script, ScriptTagRelation
from apps.tags.models import Tag
from apps.tags.serializers import TagBriefSerializer
from apps.users.serializers import UserSerializer
import re
import logging
from django.db import transaction

logger = logging.getLogger(__name__)

class ScriptTagRelationSerializer(serializers.ModelSerializer):
    """话术标签关联序列化器"""
    tag_name = serializers.CharField(source='tag.tag_name', read_only=True)
    
    class Meta:
        model = ScriptTagRelation
        fields = ['id', 'script', 'tag', 'tag_name', 'created_at']
        read_only_fields = ['created_at']

    def validate(self, data):
        """验证数据 - 使用select_related减少查询"""
        tag = Tag.objects.select_related().get(id=data['tag'].id)
        if not tag.is_active:
            raise serializers.ValidationError({'tag': '不能关联未启用的标签'})
        return data

class ScriptSerializer(serializers.ModelSerializer):
    """话术序列化器"""
    tags = TagBriefSerializer(many=True, read_only=True)
    tag_relations = ScriptTagRelationSerializer(
        source='script_tag_relations',
        many=True,
        read_only=True
    )
    tag_ids = serializers.ListField(
        child=serializers.IntegerField(),
        write_only=True,
        required=False
    )
    created_by_name = serializers.CharField(source='created_by.name', read_only=True)
    updated_by_name = serializers.CharField(source='updated_by.name', read_only=True)
    
    class Meta:
        model = Script
        fields = [
            'id', 'title', 'content', 'script_type', 'is_active',
            'sort_order', 'version', 'tags', 'tag_relations', 'tag_ids',
            'created_by', 'updated_by', 'created_at', 'updated_at',
            'created_by_name', 'updated_by_name'
        ]
        read_only_fields = [
            'version', 'created_by', 'updated_by', 'created_at', 'updated_at'
        ]

    def validate_title(self, value):
        """验证标题"""
        if not value or not value.strip():
            raise serializers.ValidationError("标题不能为空")
        return value.strip()

    def validate_content(self, value):
        """验证内容"""
        if not value or not value.strip():
            raise serializers.ValidationError("内容不能为空")
        return value.strip()

    def validate_tag_ids(self, value):
        """验证标签ID列表 - 优化查询"""
        if not value:
            return value
            
        # 使用一次查询获取所有标签
        tags = Tag.objects.filter(id__in=value).values('id', 'tag_name', 'is_active')
        found_ids = {tag['id'] for tag in tags}
        
        # 检查缺失的标签
        missing_ids = set(value) - found_ids
        if missing_ids:
            raise serializers.ValidationError(f"标签不存在: {missing_ids}")
            
        # 检查未启用的标签
        inactive_tags = [tag['tag_name'] for tag in tags if not tag['is_active']]
        if inactive_tags:
            raise serializers.ValidationError(f"以下标签未启用：{', '.join(inactive_tags)}")
            
        return value

    def create(self, validated_data):
        """创建话术 - 使用事务和批量操作"""
        logger.info(f"开始创建话术，输入数据: {validated_data}")
        tag_ids = validated_data.pop('tag_ids', []) if 'tag_ids' in validated_data else []
        logger.info(f"处理标签ID列表: {tag_ids}")
        user = validated_data.get('created_by')
        logger.info(f"创建用户: {user}")
        
        try:
            with transaction.atomic():
                # 创建话术
                logger.info(f"准备创建话术，数据: {validated_data}")
                script = super().create(validated_data)
                logger.info(f"话术创建成功: ID={script.id}, 标题={script.title}")
                
                # 批量创建标签关联
                if tag_ids:
                    logger.info(f"开始创建标签关联，标签数量: {len(tag_ids)}")
                    relations = [
                        ScriptTagRelation(
                            script=script,
                            tag_id=tag_id,
                            created_by=user,
                            updated_by=user
                        ) for tag_id in tag_ids
                    ]
                    ScriptTagRelation.objects.bulk_create(relations)
                    logger.info(f"标签关联创建成功，数量: {len(relations)}")
                    
                logger.info(f"话术创建完成: ID={script.id}, 标题={script.title}")
                return script
                
        except Exception as e:
            logger.error(f"创建话术失败: {str(e)}", exc_info=True)
            raise serializers.ValidationError(f"创建话术失败: {str(e)}")

    def update(self, instance, validated_data):
        """更新话术 - 优化查询和更新"""
        with transaction.atomic():
            tag_ids = validated_data.pop('tag_ids', None)
            user = validated_data.get('updated_by')
            
            # 记录更新的字段
            update_fields = []
            for attr, value in validated_data.items():
                if getattr(instance, attr) != value:
                    setattr(instance, attr, value)
                    update_fields.append(attr)
            
            if update_fields:
                instance.save(update_fields=update_fields)
            
            # 如果提供了tag_ids，更新标签关联
            if tag_ids is not None:
                # 获取现有标签
                current_tags = set(instance.tags.values_list('id', flat=True))
                new_tags = set(tag_ids)
                
                # 计算需要添加和删除的标签
                tags_to_add = new_tags - current_tags
                tags_to_remove = current_tags - new_tags
                
                if tags_to_add or tags_to_remove:
                    # 删除需要移除的标签关联
                    if tags_to_remove:
                        ScriptTagRelation.objects.filter(
                            script=instance,
                            tag_id__in=tags_to_remove
                        ).delete()
                    
                    # 批量创建新的标签关联
                    if tags_to_add:
                        relations = [
                            ScriptTagRelation(
                                script=instance,
                                tag_id=tag_id,
                                created_by=user,
                                updated_by=user
                            ) for tag_id in tags_to_add
                        ]
                        ScriptTagRelation.objects.bulk_create(relations)
            
            return instance

class ScriptBriefSerializer(serializers.ModelSerializer):
    """话术简要信息序列化器（用于列表展示）"""
    tag_count = serializers.IntegerField(read_only=True)
    
    class Meta:
        model = Script
        fields = [
            'id', 'title', 'script_type', 'is_active',
            'version', 'tag_count', 'updated_at'
        ]

class ScriptImportSerializer(serializers.Serializer):
    """话术导入序列化器"""
    file = serializers.FileField(required=True)
    tag_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=False
    )

    def validate_file(self, value):
        """验证上传的文件"""
        # 检查文件大小
        if value.size > 5 * 1024 * 1024:  # 5MB
            raise serializers.ValidationError("文件大小不能超过5MB")

        # 检查文件类型
        allowed_types = ['text/plain', 'text/csv', 'application/vnd.ms-excel']
        if value.content_type not in allowed_types:
            raise serializers.ValidationError("只支持txt、csv文件格式")

        return value
