from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from django_filters import rest_framework as django_filters
from django.db.models import Count, Q
from django.db import transaction, IntegrityError
from django.utils import timezone
from django.core.exceptions import ObjectDoesNotExist, ValidationError as DjangoValidationError
from django.http import Http404
from django.shortcuts import get_object_or_404
import logging
import traceback
from rest_framework.exceptions import ValidationError

from .models import Tag
from .serializers import TagSerializer, TagBriefSerializer, TagTreeSerializer
from apps.scripts.serializers import ScriptBriefSerializer
from apps.scripts.models import ScriptTagRelation

logger = logging.getLogger(__name__)

class TagFilter(django_filters.FilterSet):
    """标签过滤器"""
    tag_name = django_filters.CharFilter(lookup_expr='icontains')
    is_active = django_filters.BooleanFilter()
    parent = django_filters.NumberFilter(field_name='parent', lookup_expr='exact')
    no_parent = django_filters.BooleanFilter(field_name='parent', lookup_expr='isnull')
    
    class Meta:
        model = Tag
        fields = ['tag_name', 'is_active', 'parent']

class TagViewSet(viewsets.ModelViewSet):
    """
    标签视图集
    提供标签的增删改查功能
    """
    queryset = Tag.objects.all()
    serializer_class = TagSerializer
    filterset_class = TagFilter
    search_fields = ['tag_name', 'description']
    ordering_fields = ['sort_order', 'tag_name', 'created_at']
    ordering = ['sort_order', 'tag_name']
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        """
        根据不同的操作返回不同的权限
        """
        logger.debug(f"Action: {self.action}, Permission classes: {self.permission_classes}")
        if self.action in ['create', 'update', 'partial_update', 'destroy', 'activate', 'deactivate']:
            self.permission_classes = [IsAdminUser]
        return super().get_permissions()

    def get_queryset(self):
        """
        获取查询集
        根据用户权限返回不同的查询集
        """
        try:
            queryset = super().get_queryset()
            user = self.request.user
            
            if not user.has_perm('tags.can_view_inactive_tags'):
                queryset = queryset.filter(is_active=True)
                logger.debug(f"User {user.name} can only view active tags")
            else:
                logger.debug(f"User {user.name} can view all tags")
                
            return queryset.order_by('sort_order', 'tag_name')
        except Exception as e:
            logger.error(f"Error in get_queryset: {str(e)}")
            raise

    def get_serializer_class(self):
        """
        根据不同的操作返回不同的序列化器
        """
        if self.action == 'list':
            return TagBriefSerializer
        elif self.action == 'tree':
            return TagTreeSerializer
        return TagSerializer

    def get_object(self):
        """
        获取对象，并处理不存在的情况
        """
        try:
            obj = super().get_object()
            logger.debug(f"Retrieved tag: {obj.tag_name}")
            return obj
        except Http404:
            logger.error("Tag not found")
            raise Http404("标签不存在")
        except Exception as e:
            logger.error(f"Error retrieving tag: {str(e)}\n{traceback.format_exc()}")
            raise

    def perform_create(self, serializer):
        """
        创建标签时的处理
        """
        try:
            user = self.request.user
            logger.info(f"Creating new tag by user: {user.name}")
            tag = serializer.save(created_by=user, updated_by=user)
            logger.info(f"Tag created successfully: {tag.tag_name} (ID: {tag.id})")
        except IntegrityError as e:
            logger.error(f"Database integrity error while creating tag: {str(e)}")
            raise ValidationError("标签创建失败：数据完整性错误")
        except Exception as e:
            logger.error(f"Error creating tag: {str(e)}\n{traceback.format_exc()}")
            raise ValidationError(f"标签创建失败：{str(e)}")

    def perform_update(self, serializer):
        """
        更新标签时的处理
        """
        try:
            user = self.request.user
            instance = serializer.instance
            logger.info(f"Updating tag {instance.tag_name} (ID: {instance.id}) by user: {user.name}")
            tag = serializer.save(updated_by=user)
            logger.info(f"Tag updated successfully: {tag.tag_name} (ID: {tag.id})")
        except IntegrityError as e:
            logger.error(f"Database integrity error while updating tag: {str(e)}")
            raise ValidationError("标签更新失败：数据完整性错误")
        except Exception as e:
            logger.error(f"Error updating tag: {str(e)}\n{traceback.format_exc()}")
            raise ValidationError(f"标签更新失败：{str(e)}")

    def destroy(self, request, *args, **kwargs):
        """删除标签"""
        tag = self.get_object()
        tag_name = tag.tag_name
        tag_id = tag.id
        logger.info(f"Attempting to delete tag: {tag_name} (ID: {tag_id})")
        
        # 检查是否有子标签
        if tag.children.exists():
            logger.warning(f"Cannot delete tag {tag_name} (ID: {tag_id}): has child tags")
            return Response(
                {'error': '无法删除存在子标签的标签'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # 检查是否有关联的话术
        if tag.script_tag_relations.exists():
            logger.warning(f"Cannot delete tag {tag_name} (ID: {tag_id}): has associated scripts")
            return Response(
                {'error': '无法删除已被话术使用的标签'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            tag.delete()
            logger.info(f"Tag deleted successfully: {tag_name} (ID: {tag_id})")
            return Response(status=status.HTTP_204_NO_CONTENT)
        except Exception as e:
            logger.error(f"Error deleting tag {tag_name} (ID: {tag_id}): {str(e)}")
            return Response(
                {'error': '删除标签时发生错误'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=False, methods=['get'])
    def tree(self, request):
        """
        获取标签树形结构
        """
        try:
            # 只获取顶级标签
            root_tags = Tag.objects.filter(parent=None).order_by('sort_order', 'tag_name')
            
            # 如果用户没有查看未启用标签的权限，则只返回已启用的标签
            if not request.user.has_perm('tags.can_view_inactive_tags'):
                root_tags = root_tags.filter(is_active=True)
            
            serializer = TagTreeSerializer(root_tags, many=True)
            return Response(serializer.data)
        except Exception as e:
            logger.error(f"Error retrieving tag tree: {str(e)}")
            return Response(
                {'error': '获取标签树失败'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=True, methods=['post'])
    def activate(self, request, *args, **kwargs):
        """
        激活标签
        """
        try:
            tag = Tag.objects.get(pk=kwargs.get('pk'))
            logger.info(f"Attempting to activate tag: {tag} (ID: {tag.id})")

            if tag.parent and not tag.parent.is_active:
                logger.warning(f"Cannot activate tag {tag} (ID: {tag.id}): parent tag is inactive")
                return Response({"detail": "父标签处于停用状态"}, status=status.HTTP_400_BAD_REQUEST)

            tag.is_active = True
            tag.save()
            logger.info(f"Tag activated successfully: {tag} (ID: {tag.id})")
            return Response({"detail": "标签已激活"}, status=status.HTTP_200_OK)

        except Tag.DoesNotExist:
            logger.error("Tag not found")
            raise Http404("标签不存在")
        except Exception as e:
            logger.error(f"Error activating tag: {str(e)}")
            raise

    @action(detail=True, methods=['post'])
    def deactivate(self, request, pk=None):
        """
        停用标签
        """
        try:
            tag = self.get_object()
            logger.info(f"Attempting to deactivate tag: {tag.tag_name} (ID: {tag.id})")
            
            # 获取受影响的子标签数量
            affected_children = tag.get_all_children().count()
            
            tag.deactivate()
            
            logger.info(f"Tag deactivated successfully: {tag.tag_name} (ID: {tag.id})")
            return Response({
                'status': 'success',
                'message': '标签已停用',
                'tag': TagBriefSerializer(tag).data,
                'affected_children': affected_children
            })
            
        except Http404:
            logger.error("Tag not found for deactivation")
            return Response(
                {'error': '标签不存在', 'code': 'not_found'},
                status=status.HTTP_404_NOT_FOUND
            )
        except ValidationError as e:
            logger.error(f"Validation error while deactivating tag: {str(e)}")
            return Response(
                {
                    'error': '标签停用失败',
                    'code': 'validation_error',
                    'detail': str(e)
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Error deactivating tag: {str(e)}\n{traceback.format_exc()}")
            return Response(
                {
                    'error': '标签停用失败',
                    'code': 'deactivation_error',
                    'detail': str(e)
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=True, methods=['get'])
    def usage(self, request, pk=None):
        """获取标签使用情况"""
        tag = self.get_object()
        logger.info(f"开始获取标签使用情况: tag_id={tag.id}, tag_name={tag.tag_name}")
        
        try:
            # 获取使用该标签的话术数量
            usage_count = tag.script_tag_relations.count()
            logger.info(f"标签关联话术数量: {usage_count}")
            
            # 获取使用该标签的话术列表
            relations = tag.script_tag_relations.select_related('script').all()
            logger.info(f"成功获取标签关联关系列表，数量: {len(relations)}")
            
            scripts = [relation.script for relation in relations]
            logger.info(f"提取话术列表完成，数量: {len(scripts)}")
            
            # 序列化话术数据
            script_data = ScriptBriefSerializer(scripts, many=True).data
            logger.info(f"话术数据序列化完成，序列化后数量: {len(script_data)}")
            
            response_data = {
                'tag_name': tag.tag_name,
                'usage_count': usage_count,
                'scripts': script_data
            }
            logger.info(f"返回数据准备完成: tag_name={tag.tag_name}, usage_count={usage_count}")
            
            return Response(response_data)
            
        except Exception as e:
            logger.error(f"获取标签使用情况时发生错误: {str(e)}", exc_info=True)
            return Response({
                'status': 'error',
                'message': f'获取标签使用情况失败: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['post'])
    def bulk_create(self, request):
        """批量创建标签"""
        tag_names = request.data.get('tag_names', [])
        if not tag_names:
            return Response({
                'status': 'error',
                'message': '请提供标签名称列表'
            }, status=status.HTTP_400_BAD_REQUEST)

        created_tags = []
        errors = []
        
        with transaction.atomic():
            for tag_name in tag_names:
                serializer = self.get_serializer(data={'tag_name': tag_name})
                if serializer.is_valid():
                    tag = serializer.save()
                    created_tags.append(TagBriefSerializer(tag).data)
                else:
                    errors.append({
                        'tag_name': tag_name,
                        'errors': serializer.errors
                    })

        return Response({
            'status': 'success',
            'created_count': len(created_tags),
            'duplicates': [],
            'errors': errors
        })

    @action(detail=False, methods=['post'])
    def bulk_delete(self, request):
        """批量删除标签"""
        tag_ids = request.data.get('ids', [])
        if not tag_ids:
            return Response({
                'status': 'error',
                'message': '请提供要删除的标签ID列表'
            }, status=status.HTTP_400_BAD_REQUEST)

        # 检查标签是否在使用中
        used_tags = Tag.objects.filter(
            id__in=tag_ids,
            script_tag_relations__isnull=False
        ).distinct()

        if used_tags.exists():
            used_tag_names = [tag.tag_name for tag in used_tags]
            return Response({
                'status': 'error',
                'message': '以下标签正在使用中，无法删除',
                'used_tags': used_tag_names
            }, status=status.HTTP_400_BAD_REQUEST)

        # 删除未使用的标签
        deleted_count = Tag.objects.filter(
            id__in=tag_ids,
            script_tag_relations__isnull=True
        ).delete()[0]

        return Response({
            'status': 'success',
            'message': f'成功删除{deleted_count}个标签'
        })

    @action(detail=False, methods=['get'])
    def usage_statistics(self, request):
        """获取标签使用统计信息"""
        tags = self.get_queryset().values('id', 'tag_name', 'usage_count')
        
        # 计算统计信息
        total_tags = len(tags)
        total_usage = sum(tag['usage_count'] for tag in tags)
        unused_tags = sum(1 for tag in tags if tag['usage_count'] == 0)
        
        return Response({
            'total_tags': total_tags,
            'total_usage': total_usage,
            'unused_tags': unused_tags,
            'tags': tags
        })

    @action(detail=False, methods=['get'])
    def search_suggestions(self, request):
        """获取标签搜索建议"""
        keyword = request.query_params.get('keyword', '')
        if not keyword:
            return Response([])
            
        tags = Tag.objects.filter(
            tag_name__icontains=keyword
        ).values('id', 'tag_name')[:10]  # 限制返回10个建议
        
        return Response(list(tags))
