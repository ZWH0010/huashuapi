from django_filters import rest_framework as django_filters
from .models import Script, Tag

class ScriptFilter(django_filters.FilterSet):
    """话术过滤器"""
    title = django_filters.CharFilter(lookup_expr='icontains')
    content = django_filters.CharFilter(lookup_expr='icontains')
    script_type = django_filters.ChoiceFilter(choices=Script.SCRIPT_TYPES)
    is_active = django_filters.BooleanFilter()
    tag = django_filters.NumberFilter(field_name='tags', method='filter_by_tag')
    created_after = django_filters.DateTimeFilter(field_name='created_at', lookup_expr='gte')
    created_before = django_filters.DateTimeFilter(field_name='created_at', lookup_expr='lte')
    tags = django_filters.ModelMultipleChoiceFilter(
        field_name='tags',
        queryset=Tag.objects.all(),
        method='filter_by_tags'
    )
    
    class Meta:
        model = Script
        fields = ['title', 'content', 'script_type', 'is_active', 'tags']
        
    def filter_by_tag(self, queryset, name, value):
        """按单个标签过滤"""
        return queryset.filter(tags__id=value).distinct()
        
    def filter_by_tags(self, queryset, name, value):
        """按多个标签过滤"""
        if not value:
            return queryset
        for tag in value:
            queryset = queryset.filter(tags=tag)
        return queryset.distinct() 