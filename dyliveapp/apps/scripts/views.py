from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from django_filters import rest_framework as django_filters
from django.db.models import Count, Q, Max
from django.db import transaction, DatabaseError
from django.core.exceptions import ValidationError
from django.http import Http404, HttpResponse
import logging
import csv
import io
import codecs
from datetime import datetime
import re
from django.db.models import Prefetch
import time
import threading
from django.db.utils import OperationalError
from django.utils import timezone
from collections import Counter

from .models import Script, ScriptTagRelation, Tag
from .serializers import (
    ScriptSerializer, ScriptBriefSerializer,
    ScriptImportSerializer, ScriptTagRelationSerializer
)
from .filters import ScriptFilter
from .cache import ScriptCacheManager

logger = logging.getLogger(__name__)

class ScriptViewSet(viewsets.ModelViewSet):
    """
    话术视图集
    提供话术的增删改查功能
    """
    queryset = Script.objects.all()
    serializer_class = ScriptSerializer
    permission_classes = [IsAuthenticated]
    filterset_class = ScriptFilter
    search_fields = ['title', 'content']
    ordering_fields = ['sort_order', 'created_at', 'updated_at']
    ordering = ['-sort_order', '-updated_at']

    def get_object(self):
        """获取单个对象，优先从缓存获取"""
        script_id = self.kwargs.get('pk')
        if script_id:
            # 尝试从缓存获取
            cached_data = ScriptCacheManager.get_cached_script(int(script_id))
            if cached_data:
                return Script(**cached_data)
        
        # 缓存未命中，从数据库获取
        instance = super().get_object()
        # 缓存数据
        if instance:
            ScriptCacheManager.cache_script(instance.id, self.get_serializer(instance).data)
        return instance

    def list(self, request, *args, **kwargs):
        """获取列表，优先从缓存获取"""
        # 尝试从缓存获取
        cache_params = request.query_params.dict()
        cached_data = ScriptCacheManager.get_cached_script_list(cache_params)
        if cached_data:
            return Response(cached_data)
        
        # 缓存未命中，从数据库获取
        response = super().list(request, *args, **kwargs)
        # 缓存数据
        ScriptCacheManager.cache_script_list(cache_params, response.data)
        return response

    def get_permissions(self):
        """根据不同的操作设置不同的权限"""
        if self.action in ['search']:
            return []
        return super().get_permissions()

    def get_queryset(self):
        """获取查询集"""
        queryset = super().get_queryset()
        
        # 添加标签数量统计
        queryset = queryset.annotate(tag_count=Count('tags'))
        
        # 如果用户没有查看未启用话术的权限，则只返回已启用的话术
        user = self.request.user
        if not user.has_perm('scripts.can_view_inactive_scripts'):
            queryset = queryset.filter(is_active=True)
            
        return queryset

    def get_serializer_class(self):
        """根据不同的操作返回不同的序列化器"""
        if self.action == 'list':
            return ScriptBriefSerializer
        elif self.action == 'import_scripts':
            return ScriptImportSerializer
        return ScriptSerializer

    def perform_create(self, serializer):
        """创建话术时的处理"""
        try:
            with transaction.atomic():
                script = serializer.save(
                    created_by=self.request.user,
                    updated_by=self.request.user
                )
                # 使列表缓存失效
                ScriptCacheManager.invalidate_script_list_cache()
                logger.info(f"Script created successfully: {script.title} (ID: {script.id})")
        except Exception as e:
            logger.error(f"Error creating script: {str(e)}")
            raise

    def perform_update(self, serializer):
        """更新话术时的处理"""
        try:
            with transaction.atomic():
                script = serializer.save(updated_by=self.request.user)
                # 使相关缓存失效
                ScriptCacheManager.invalidate_script_cache(script.id)
                ScriptCacheManager.invalidate_script_list_cache()
                ScriptCacheManager.invalidate_script_versions_cache(script.title)
                logger.info(f"Script updated successfully: {script.title} (ID: {script.id})")
        except Exception as e:
            logger.error(f"Error updating script: {str(e)}")
            raise

    def perform_destroy(self, instance):
        """删除话术时的处理"""
        try:
            title = instance.title
            instance_id = instance.id
            # 使相关缓存失效
            ScriptCacheManager.invalidate_script_cache(instance_id)
            ScriptCacheManager.invalidate_script_list_cache()
            ScriptCacheManager.invalidate_script_versions_cache(title)
            
            instance.delete()
            logger.info(f"Script deleted successfully: {title} (ID: {instance_id})")
        except Exception as e:
            logger.error(f"Error deleting script: {str(e)}")
            raise

    @action(detail=True, methods=['get'])
    def versions(self, request, pk=None):
        """获取所有版本"""
        try:
            script = self.get_object()
            # 尝试从缓存获取版本列表
            cached_versions = ScriptCacheManager.get_cached_script_versions(script.title)
            if cached_versions:
                return Response(cached_versions)
            
            # 缓存未命中，从数据库获取
            versions = Script.objects.filter(
                title=script.title
            ).order_by('-version')
            
            serializer = ScriptBriefSerializer(versions, many=True)
            # 缓存版本列表
            ScriptCacheManager.cache_script_versions(script.title, serializer.data)
            return Response(serializer.data)
        except Http404:
            return Response(
                {'error': '话术不存在'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Error retrieving versions: {str(e)}")
            return Response(
                {'error': f"获取版本列表失败：{str(e)}"},
                status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=True, methods=['post'])
    def new_version(self, request, pk=None):
        """创建话术新版本"""
        thread_name = threading.current_thread().name
        logger.info(f"[Thread {thread_name}] 开始处理创建新版本请求: script_id={pk}")
        
        retry_count = 0
        max_retries = 3
        retry_delay = 1  # 初始重试延迟（秒）
        
        while retry_count < max_retries:
            try:
                with transaction.atomic():
                    # 获取原始话术，使用 select_for_update 加锁
                    logger.info(f"[Thread {thread_name}] 尝试获取原始话术: ID={pk}")
                    script = Script.objects.select_related('created_by')\
                        .select_for_update(nowait=False)\
                        .get(pk=pk)
                    logger.info(f"[Thread {thread_name}] 成功获取原始话术: ID={script.id}, Title={script.title}, Version={script.version}")
                    
                    # 创建新版本
                    logger.info(f"[Thread {thread_name}] 开始创建新版本")
                    new_script = script.create_new_version(created_by=request.user)
                    logger.info(f"[Thread {thread_name}] 新版本创建成功: ID={new_script.id}, Title={new_script.title}, Version={new_script.version}")
                    
                    # 使相关缓存失效
                    ScriptCacheManager.invalidate_script_list_cache()
                    ScriptCacheManager.invalidate_script_versions_cache(script.title)
                    
                    # 序列化结果
                    logger.info(f"[Thread {thread_name}] 开始序列化新版本数据")
                    serializer = self.get_serializer(new_script)
                    # 缓存新版本数据
                    ScriptCacheManager.cache_script(new_script.id, serializer.data)
                    logger.info(f"[Thread {thread_name}] 序列化完成，准备返回数据")
                    
                    return Response(serializer.data, status=status.HTTP_201_CREATED)
                
            except Script.DoesNotExist:
                logger.error(f"[Thread {thread_name}] 话术不存在: ID={pk}")
                return Response(
                    {'error': '话术不存在'},
                    status=status.HTTP_404_NOT_FOUND
                )
            except OperationalError as e:
                retry_count += 1
                if retry_count >= max_retries:
                    logger.error(f"[Thread {thread_name}] 数据库操作错误，已达到最大重试次数: {str(e)}", exc_info=True)
                    return Response(
                        {'error': '数据库操作错误，请稍后重试'},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR
                    )
                
                # 使用指数退避策略
                wait_time = retry_delay * (2 ** (retry_count - 1))
                logger.warning(f"[Thread {thread_name}] 第 {retry_count} 次重试，等待 {wait_time} 秒后重试")
                time.sleep(wait_time)
                continue
                
            except Exception as e:
                logger.error(f"[Thread {thread_name}] 创建新版本时发生错误: {str(e)}", exc_info=True)
                return Response(
                    {'error': f'创建新版本失败: {str(e)}'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )

    @action(detail=False, methods=['get'])
    def types(self, request):
        """获取所有话术类型"""
        return Response(dict(Script.SCRIPT_TYPE_CHOICES))

    @action(detail=False, methods=['post'])
    def bulk_delete(self, request):
        """批量删除话术"""
        try:
            logger.info(f"Starting bulk delete operation with request data: {request.data}")
            script_ids = request.data.get('script_ids', [])
            
            if not script_ids:
                logger.warning("No script_ids provided in request")
                return Response(
                    {'detail': '请选择要删除的话术'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # 获取要删除的话术
            scripts = Script.objects.filter(id__in=script_ids)
            logger.info(f"Found {scripts.count()} scripts to delete out of {len(script_ids)} requested")
            
            if not scripts.exists():
                logger.warning(f"No scripts found with ids: {script_ids}")
                return Response(
                    {'detail': '未找到要删除的话术'},
                    status=status.HTTP_404_NOT_FOUND
                )

            # 记录删除数量
            delete_count = scripts.count()
            logger.info(f"Preparing to delete {delete_count} scripts")

            # 删除话术
            with transaction.atomic():
                # 记录要删除的话术信息
                for script in scripts:
                    logger.info(f"Deleting script: ID={script.id}, Title={script.title}, Version={script.version}")
                
                scripts.delete()
                logger.info(f"Successfully deleted {delete_count} scripts")

            return Response({
                'detail': f'成功删除{delete_count}个话术',
                'delete_count': delete_count
            })

        except Exception as e:
            logger.error(f"Error in bulk delete operation: {str(e)}", exc_info=True)
            return Response(
                {'detail': f'批量删除失败：{str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=False, methods=['post'])
    def bulk_update_status(self, request):
        """批量更新话术状态"""
        try:
            ids = request.data.get('ids', [])
            is_active = request.data.get('is_active')
            
            if not ids or is_active is None:
                return Response(
                    {'error': '请提供要更新的话术ID列表和状态'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # 更新状态
            updated_count = Script.objects.filter(id__in=ids).update(
                is_active=is_active,
                updated_by=request.user
            )
            
            status_text = '启用' if is_active else '停用'
            return Response({
                'message': f'成功{status_text}{updated_count}个话术',
                'updated_count': updated_count
            })
        except Exception as e:
            logger.error(f"Error bulk updating script status: {str(e)}")
            return Response(
                {'error': f"批量更新状态失败：{str(e)}"},
                status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=False, methods=['post'])
    def bulk_create(self, request):
        """批量创建话术"""
        serializer = self.get_serializer(data=request.data, many=True)
        serializer.is_valid(raise_exception=True)
        self.perform_bulk_create(serializer)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def perform_bulk_create(self, serializer):
        """执行批量创建"""
        serializer.save()

    @action(detail=False, methods=['get'])
    def search_by_tags(self, request):
        """按标签组合搜索话术"""
        tag_ids = request.query_params.getlist('tag_ids[]', [])
        if not tag_ids:
            return Response({
                'status': 'error',
                'message': '请提供标签ID列表'
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            tag_ids = [int(tag_id) for tag_id in tag_ids]
        except ValueError:
            return Response({
                'status': 'error',
                'message': '标签ID必须是数字'
            }, status=status.HTTP_400_BAD_REQUEST)

        # 构建查询条件：话术必须包含所有指定的标签
        queryset = self.get_queryset()
        for tag_id in tag_ids:
            queryset = queryset.filter(tags__id=tag_id)

        serializer = ScriptBriefSerializer(queryset, many=True)
        return Response({
            'status': 'success',
            'data': serializer.data
        })

    @action(detail=True, methods=['post'])
    def update_tags(self, request, pk=None):
        """更新话术的标签"""
        script = self.get_object()
        tag_ids = request.data.get('tag_ids', [])

        serializer = self.get_serializer(script, data={'tag_ids': tag_ids}, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response({
            'status': 'success',
            'message': '标签更新成功',
            'data': serializer.data
        })

    @action(detail=False, methods=['get'])
    def by_tag(self, request):
        """根据标签获取话术列表"""
        tag_id = request.query_params.get('tag_id')
        if not tag_id:
            return Response({
                'status': 'error',
                'message': '请提供标签ID'
            }, status=status.HTTP_400_BAD_REQUEST)
            
        scripts = self.get_queryset().filter(tags__id=tag_id)
        page = self.paginate_queryset(scripts)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
            
        serializer = self.get_serializer(scripts, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def search(self, request):
        """
        搜索话术
        支持按标题、内容、标签进行搜索
        """
        try:
            # 尝试从缓存获取搜索结果
            cache_params = request.query_params.dict()
            cached_data = ScriptCacheManager.get_cached_script_list(cache_params)
            if cached_data:
                return Response(cached_data)
            
            # 缓存未命中，执行搜索
            keyword = request.query_params.get('keyword', '').strip()
            tag_ids = request.query_params.getlist('tag_ids', [])
            script_type = request.query_params.get('script_type')
            is_active = request.query_params.get('is_active')
            
            logger.info(f"收到搜索请求: keyword='{keyword}', tag_ids={tag_ids}, script_type={script_type}, is_active={is_active}")
            
            # 构建基础查询集
            queryset = Script.objects.all()
            logger.info(f"初始查询集数量: {queryset.count()}")
            
            # 关键词搜索
            if keyword:
                logger.info(f"应用关键词过滤: '{keyword}'")
                queryset = queryset.filter(
                    Q(title__icontains=keyword) |
                    Q(content__icontains=keyword)
                )
                logger.info(f"关键词过滤后数量: {queryset.count()}")
            
            # 标签过滤
            if tag_ids:
                logger.info(f"应用标签过滤: {tag_ids}")
                for tag_id in tag_ids:
                    queryset = queryset.filter(tags__id=tag_id)
                logger.info(f"标签过滤后数量: {queryset.count()}")
            
            # 类型过滤
            if script_type:
                logger.info(f"应用类型过滤: {script_type}")
                queryset = queryset.filter(script_type=script_type)
                logger.info(f"类型过滤后数量: {queryset.count()}")
            
            # 状态过滤
            if is_active is not None:
                is_active = is_active.lower() == 'true'
                logger.info(f"应用状态过滤: is_active={is_active}")
                queryset = queryset.filter(is_active=is_active)
                logger.info(f"状态过滤后数量: {queryset.count()}")
            
            # 去重
            queryset = queryset.distinct()
            logger.info(f"去重后最终数量: {queryset.count()}")
            
            # 分页
            page = self.paginate_queryset(queryset)
            if page is not None:
                serializer = self.get_serializer(page, many=True)
                response_data = self.get_paginated_response(serializer.data).data
                # 缓存搜索结果
                ScriptCacheManager.cache_script_list(cache_params, response_data)
                logger.info(
                    "返回分页搜索结果: "
                    f"总数={response_data['count']}, "
                    f"当前页数量={len(response_data['results'])}, "
                    f"是否有下一页={'next' in response_data and response_data['next'] is not None}"
                )
                return Response(response_data)
            
            serializer = self.get_serializer(queryset, many=True)
            result_data = serializer.data
            # 缓存搜索结果
            ScriptCacheManager.cache_script_list(cache_params, result_data)
            logger.info(
                "返回完整搜索结果: "
                f"结果数量={len(result_data)}, "
                f"话术类型统计={Counter(item['script_type'] for item in result_data)}"
            )
            return Response(result_data)
            
        except Exception as e:
            logger.error(f"搜索过程中发生错误: {str(e)}", exc_info=True)
            return Response(
                {'error': f'搜索失败: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=True, methods=['post'])
    def copy(self, request, pk=None):
        """复制话术"""
        original_script = self.get_object()
        
        # 创建新话术
        new_script = Script.objects.create(
            content=original_script.content,
            user=request.user
        )
        
        # 复制标签关联
        for tag in original_script.tags.all():
            ScriptTagRelation.objects.create(
                script=new_script,
                tag=tag
            )
        
        serializer = self.get_serializer(new_script)
        return Response({
            'status': 'success',
            'message': '话术复制成功',
            'data': serializer.data
        })

    @action(detail=False, methods=['POST'])
    def import_scripts(self, request):
        """导入话术"""
        try:
            logger.info("Starting script import process")
            
            # 验证上传的文件
            serializer = ScriptImportSerializer(data=request.data)
            if not serializer.is_valid():
                logger.warning(f"Import validation failed: {serializer.errors}")
                return Response(
                    {'error': serializer.errors},
                    status=status.HTTP_400_BAD_REQUEST
                )

            file = serializer.validated_data['file']
            tag_ids = serializer.validated_data.get('tag_ids', [])

            # 读取CSV文件
            try:
                csv_data = file.read().decode('utf-8-sig').splitlines()
            except UnicodeDecodeError:
                logger.error("Failed to decode CSV file")
                return Response(
                    {'error': '文件编码错误，请使用UTF-8编码'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            if not csv_data:
                logger.warning("Empty CSV file uploaded")
                return Response(
                    {'error': '文件内容为空'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # 解析CSV头部
            header = next(iter(csv_data), None)
            if not header:
                logger.warning("No header found in CSV file")
                return Response(
                    {'error': '文件格式错误：缺少标题行'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            required_columns = ['标题', '内容', '话术类型']
            header_columns = [col.strip() for col in header.split(',')]
            
            # 验证必需列
            missing_columns = [col for col in required_columns if col not in header_columns]
            if missing_columns:
                logger.warning(f"Missing required columns: {missing_columns}")
                return Response(
                    {'error': f'文件格式错误：缺少必需列 {", ".join(missing_columns)}'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # 处理每一行数据
            created_count = 0
            error_rows = []
            
            for row_number, line in enumerate(csv_data[1:], start=2):
                try:
                    # 解析行数据
                    row_data = [col.strip() for col in line.split(',')]
                    if len(row_data) < 3:
                        error_rows.append({
                            'row': row_number,
                            'error': '数据列数不足'
                        })
                        continue

                    title, content, script_type = row_data[:3]
                    
                    # 基本验证
                    if not title or not content or not script_type:
                        error_rows.append({
                            'row': row_number,
                            'error': '标题、内容和话术类型不能为空'
                        })
                        continue

                    # 验证话术类型
                    if script_type not in dict(Script.SCRIPT_TYPES):
                        error_rows.append({
                            'row': row_number,
                            'error': f'无效的话术类型：{script_type}'
                        })
                        continue

                    # 创建话术
                    script = Script.objects.create(
                        title=title,
                        content=content,
                        script_type=script_type,
                        created_by=request.user,
                        updated_by=request.user
                    )

                    # 处理标签
                    if tag_ids:
                        for tag_id in tag_ids:
                            try:
                                tag = Tag.objects.get(id=tag_id, is_active=True)
                                ScriptTagRelation.objects.create(
                                    script=script,
                                    tag=tag,
                                    created_by=request.user,
                                    updated_by=request.user
                                )
                            except Tag.DoesNotExist:
                                logger.warning(f"Tag {tag_id} not found or inactive")
                                continue

                    created_count += 1
                    logger.info(f"Successfully created script: {title}")

                except Exception as e:
                    logger.error(f"Error processing row {row_number}: {str(e)}")
                    error_rows.append({
                        'row': row_number,
                        'error': str(e)
                    })

            # 返回导入结果
            result = {
                'created_count': created_count,
                'total_rows': len(csv_data) - 1,
                'success': created_count > 0
            }
            
            if error_rows:
                result['errors'] = error_rows
                logger.warning(f"Import completed with {len(error_rows)} errors")
                return Response(result, status=status.HTTP_207_MULTI_STATUS)
            
            logger.info(f"Import completed successfully. Created {created_count} scripts")
            return Response(result, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Import failed with error: {str(e)}")
            return Response(
                {'error': f'导入失败：{str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=False, methods=['get'])
    def export_scripts(self, request):
        """导出话术"""
        try:
            # 获取所有话术
            scripts = Script.objects.all()
            
            # 创建响应
            response = HttpResponse(content_type='text/csv')
            response['Content-Disposition'] = 'attachment; filename="scripts.csv"'
            
            # 创建CSV写入器
            writer = csv.writer(response)
            writer.writerow(['标题', '内容', '话术类型', '标签'])
            
            # 写入数据
            for script in scripts:
                tags = [tag.tag_name for tag in script.tags.all()]
                writer.writerow([
                    script.title,
                    script.content,
                    script.script_type,
                    ','.join(tags)
                ])
            
            return response
        except Exception as e:
            logger.error(f"Error exporting scripts: {str(e)}")
            return Response({'error': f'导出失败: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['post'])
    def batch_copy(self, request):
        """批量复制话术"""
        script_ids = request.data.get('ids', [])
        if not script_ids:
            return Response({
                'status': 'error',
                'message': '请提供要复制的话术ID列表'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        original_scripts = self.get_queryset().filter(id__in=script_ids)
        copied_scripts = []
        
        with transaction.atomic():
            for script in original_scripts:
                # 创建新话术
                new_script = Script.objects.create(
                    content=script.content,
                    user=request.user
                )
                
                # 复制标签关联
                for tag in script.tags.all():
                    ScriptTagRelation.objects.create(
                        script=new_script,
                        tag=tag
                    )
                
                copied_scripts.append(new_script)
        
        serializer = ScriptBriefSerializer(copied_scripts, many=True)
        return Response({
            'status': 'success',
            'message': f'成功复制{len(copied_scripts)}条话术',
            'data': serializer.data
        })
