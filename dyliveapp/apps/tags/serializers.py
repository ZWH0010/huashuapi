from rest_framework import serializers
from .models import Tag
from apps.scripts.models import ScriptTagRelation
import logging

logger = logging.getLogger(__name__)

class TagSerializer(serializers.ModelSerializer):
    """标签序列化器"""
    usage_count = serializers.SerializerMethodField()
    children = serializers.SerializerMethodField()
    parent_name = serializers.SerializerMethodField()
    ancestors = serializers.SerializerMethodField()
    
    class Meta:
        model = Tag
        fields = [
            'id', 'tag_name', 'description', 'is_active', 'sort_order',
            'parent', 'parent_name', 'children', 'ancestors',
            'created_by', 'updated_by', 'created_at', 'updated_at', 'usage_count'
        ]
        read_only_fields = ['created_by', 'updated_by', 'created_at', 'updated_at', 'usage_count']

    def validate_tag_name(self, value):
        """验证标签名称"""
        if not value or not value.strip():
            raise serializers.ValidationError("标签名称不能为空")
        
        value = value.strip()
        # 检查标签名称是否已存在（不区分大小写）
        if self.instance is None:  # 创建新标签时
            if Tag.objects.filter(tag_name__iexact=value).exists():
                raise serializers.ValidationError("标签名称已存在")
        else:  # 更新标签时
            if Tag.objects.filter(tag_name__iexact=value).exclude(id=self.instance.id).exists():
                raise serializers.ValidationError("标签名称已存在")
        
        return value

    def validate_parent(self, value):
        """验证父标签"""
        if value:
            # 检查父标签是否存在
            if not Tag.objects.filter(id=value.id).exists():
                raise serializers.ValidationError("父标签不存在")
            
            # 检查父标签是否已启用
            if not value.is_active:
                raise serializers.ValidationError("不能选择未启用的标签作为父标签")
            
            # 检查是否形成循环引用
            if self.instance and self.instance.pk:
                if value.pk == self.instance.pk:
                    raise serializers.ValidationError("标签不能将自己设为父标签")
                
                # 检查是否将一个子标签设为父标签
                children_pks = set(self.instance.get_all_children().values_list('pk', flat=True))
                if value.pk in children_pks:
                    raise serializers.ValidationError("不能将子标签设为父标签")
        
        return value

    def validate(self, data):
        """验证数据"""
        if self.instance:  # 更新操作
            if 'parent' in data:
                # 检查是否将一个有子标签的标签设为其他标签的子标签
                if self.instance.children.exists() and data['parent']:
                    raise serializers.ValidationError({
                        "parent": "含有子标签的标签不能设为其他标签的子标签"
                    })
        return data

    def get_usage_count(self, obj):
        """获取标签使用次数"""
        return getattr(obj, 'usage_count', ScriptTagRelation.objects.filter(tag=obj).count())

    def get_children(self, obj):
        """获取子标签"""
        # 优化查询，只获取必要的字段
        children = obj.children.all().only('id', 'tag_name')
        return TagBriefSerializer(children, many=True).data

    def get_parent_name(self, obj):
        """获取父标签名称"""
        return obj.parent.tag_name if obj.parent else None

    def get_ancestors(self, obj):
        """获取祖先标签"""
        ancestors = obj.get_ancestors()
        return TagBriefSerializer(ancestors, many=True).data

    def create(self, validated_data):
        """创建标签"""
        try:
            user = self.context['request'].user
            validated_data['created_by'] = user
            validated_data['updated_by'] = user
            
            tag = Tag.objects.create(**validated_data)
            logger.info(f"Tag created successfully: {tag.tag_name}")
            return tag
        except Exception as e:
            logger.error(f"Error creating tag: {str(e)}")
            raise serializers.ValidationError(f"创建标签失败: {str(e)}")

    def update(self, instance, validated_data):
        """更新标签"""
        try:
            validated_data['updated_by'] = self.context['request'].user
            
            for attr, value in validated_data.items():
                setattr(instance, attr, value)
            
            instance.save()
            logger.info(f"Tag updated successfully: {instance.tag_name}")
            return instance
        except Exception as e:
            logger.error(f"Error updating tag: {str(e)}")
            raise serializers.ValidationError(f"更新标签失败: {str(e)}")

class TagBriefSerializer(serializers.ModelSerializer):
    """标签简要信息序列化器（用于列表展示）"""
    usage_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Tag
        fields = ['id', 'tag_name', 'usage_count']

    def get_usage_count(self, obj):
        """获取标签使用次数"""
        return getattr(obj, 'usage_count', ScriptTagRelation.objects.filter(tag=obj).count())

class TagTreeSerializer(serializers.ModelSerializer):
    """标签树形结构序列化器"""
    children = serializers.SerializerMethodField()
    
    class Meta:
        model = Tag
        fields = ['id', 'tag_name', 'description', 'is_active', 'sort_order', 'children']
        
    def get_children(self, obj):
        """递归获取子标签"""
        # 优化查询，使用select_related减少数据库查询
        children = obj.children.all().select_related('parent').order_by('-sort_order', 'tag_name')
        return TagTreeSerializer(children, many=True).data
