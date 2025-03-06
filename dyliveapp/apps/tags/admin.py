from django.contrib import admin
from django.utils.html import format_html
from django.db.models import Count
from .models import Tag

@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    """标签管理界面"""
    list_display = ['tag_name', 'description_brief', 'parent_tag', 'is_active_icon', 
                   'sort_order', 'usage_count', 'created_at', 'updated_at']
    list_filter = ['is_active', 'parent']
    search_fields = ['tag_name', 'description']
    ordering = ['-sort_order', 'tag_name']
    readonly_fields = ['created_by', 'updated_by', 'created_at', 'updated_at']
    raw_id_fields = ['parent']
    
    def get_queryset(self, request):
        """添加使用次数统计"""
        queryset = super().get_queryset(request)
        return queryset.annotate(
            usage_count=Count('script_tag_relations')
        )
    
    def description_brief(self, obj):
        """显示简短的描述"""
        if obj.description:
            return obj.description[:50] + '...' if len(obj.description) > 50 else obj.description
        return '-'
    description_brief.short_description = '描述'
    
    def parent_tag(self, obj):
        """显示父标签"""
        return obj.parent.tag_name if obj.parent else '-'
    parent_tag.short_description = '父标签'
    
    def is_active_icon(self, obj):
        """使用图标显示是否启用"""
        if obj.is_active:
            return format_html('<span style="color: green;">✓</span>')
        return format_html('<span style="color: red;">✗</span>')
    is_active_icon.short_description = '启用状态'
    
    def usage_count(self, obj):
        """显示使用次数"""
        return getattr(obj, 'usage_count', 0)
    usage_count.short_description = '使用次数'
    
    def save_model(self, request, obj, form, change):
        """保存时自动设置创建者和更新者"""
        if not change:  # 创建时
            obj.created_by = request.user
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)
    
    fieldsets = [
        ('基本信息', {
            'fields': ['tag_name', 'description', 'is_active', 'sort_order']
        }),
        ('层级关系', {
            'fields': ['parent'],
            'classes': ['collapse']
        }),
        ('其他信息', {
            'fields': ['created_by', 'updated_by', 'created_at', 'updated_at'],
            'classes': ['collapse']
        })
    ]
