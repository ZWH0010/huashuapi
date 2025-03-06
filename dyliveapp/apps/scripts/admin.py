from django.contrib import admin
from django.utils.html import format_html
from django.db.models import Count, Prefetch
from .models import Script, ScriptTagRelation
from apps.tags.models import Tag

class ScriptTagRelationInline(admin.TabularInline):
    """话术标签关联内联管理"""
    model = ScriptTagRelation
    extra = 1
    raw_id_fields = ['tag']
    readonly_fields = ['created_by', 'updated_by', 'created_at', 'updated_at']
    
    def get_queryset(self, request):
        """优化查询 - 预加载关联数据"""
        return super().get_queryset(request).select_related(
            'tag', 'created_by', 'updated_by'
        )

@admin.register(Script)
class ScriptAdmin(admin.ModelAdmin):
    """话术管理界面"""
    list_display = [
        'title', 'script_type', 'content_preview', 'is_active_icon',
        'version', 'sort_order', 'tag_count', 'created_at', 'updated_at'
    ]
    list_filter = ['script_type', 'is_active', 'version']
    search_fields = ['title', 'content']
    ordering = ['-sort_order', '-updated_at']
    readonly_fields = ['version', 'created_by', 'updated_by', 'created_at', 'updated_at']
    inlines = [ScriptTagRelationInline]
    
    def get_queryset(self, request):
        """优化查询 - 添加统计和预加载"""
        return super().get_queryset(request).annotate(
            tag_count=Count('tags')
        ).select_related(
            'created_by', 'updated_by'
        ).prefetch_related(
            Prefetch('tags', queryset=Tag.objects.only('id', 'tag_name'))
        )
    
    def content_preview(self, obj):
        """显示内容预览"""
        if obj.content:
            return obj.content[:50] + '...' if len(obj.content) > 50 else obj.content
        return '-'
    content_preview.short_description = '内容预览'
    
    def is_active_icon(self, obj):
        """使用图标显示是否启用"""
        if obj.is_active:
            return format_html('<span style="color: green;">✓</span>')
        return format_html('<span style="color: red;">✗</span>')
    is_active_icon.short_description = '启用状态'
    
    def tag_count(self, obj):
        """显示关联的标签数量"""
        return getattr(obj, 'tag_count', 0)
    tag_count.short_description = '标签数量'
    
    def save_model(self, request, obj, form, change):
        """优化保存 - 使用事务"""
        from django.db import transaction
        with transaction.atomic():
            if not change:
                obj.created_by = request.user
            obj.updated_by = request.user
            super().save_model(request, obj, form, change)
    
    def save_formset(self, request, form, formset, change):
        """优化关联数据保存 - 批量处理"""
        instances = formset.save(commit=False)
        
        # 批量更新或创建
        to_update = []
        to_create = []
        for instance in instances:
            if instance.pk:
                instance.updated_by = request.user
                to_update.append(instance)
            else:
                instance.created_by = request.user
                instance.updated_by = request.user
                to_create.append(instance)
        
        # 批量保存
        if to_create:
            ScriptTagRelation.objects.bulk_create(to_create)
        if to_update:
            ScriptTagRelation.objects.bulk_update(
                to_update, ['updated_by', 'tag']
            )
    
    fieldsets = [
        ('基本信息', {
            'fields': ['title', 'content', 'script_type', 'is_active', 'sort_order']
        }),
        ('版本信息', {
            'fields': ['version'],
            'classes': ['collapse']
        }),
        ('其他信息', {
            'fields': ['created_by', 'updated_by', 'created_at', 'updated_at'],
            'classes': ['collapse']
        })
    ]

@admin.register(ScriptTagRelation)
class ScriptTagRelationAdmin(admin.ModelAdmin):
    """话术标签关联管理界面"""
    list_display = ['script', 'tag', 'created_by', 'created_at']
    list_filter = ['script__script_type', 'tag']
    search_fields = ['script__title', 'tag__tag_name']
    raw_id_fields = ['script', 'tag']
    readonly_fields = ['created_by', 'updated_by', 'created_at', 'updated_at']
    
    def save_model(self, request, obj, form, change):
        """保存时自动设置创建者和更新者"""
        if not change:  # 创建时
            obj.created_by = request.user
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)
    
    fieldsets = [
        ('关联信息', {
            'fields': ['script', 'tag']
        }),
        ('其他信息', {
            'fields': ['created_by', 'updated_by', 'created_at', 'updated_at'],
            'classes': ['collapse']
        })
    ]
