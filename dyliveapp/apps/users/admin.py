from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.forms import AdminPasswordChangeForm, AuthenticationForm, PasswordChangeForm
from django.utils.html import format_html
from django.urls import reverse, path
from django.contrib.auth.models import Group
from django.http import HttpResponse, JsonResponse
from django.template.response import TemplateResponse
from django.contrib.admin.views.decorators import staff_member_required
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django import forms
from django.core.exceptions import ValidationError
from django.contrib.auth import authenticate
from .models import User
import logging

logger = logging.getLogger(__name__)

class AdminAuthenticationForm(AuthenticationForm):
    """自定义管理员登录表单"""
    
    def clean(self):
        username = self.cleaned_data.get('username')
        password = self.cleaned_data.get('password')

        if username and password:
            self.user_cache = authenticate(
                self.request, username=username, password=password
            )
            
            if self.user_cache is None:
                raise ValidationError(
                    self.error_messages['invalid_login'],
                    code='invalid_login',
                    params={'username': self.username_field.verbose_name},
                )
            else:
                self.confirm_login_allowed(self.user_cache)
                
                # 检查用户是否有管理员权限
                if not (self.user_cache.is_superuser or self.user_cache.is_staff):
                    raise ValidationError(
                        "您没有权限访问管理系统。",
                        code='no_admin_permission',
                    )
                    
        return self.cleaned_data

# 设置自定义登录表单
admin.site.login_form = AdminAuthenticationForm
admin.site.site_header = '用户管理系统'
admin.site.site_title = '用户管理'
admin.site.index_title = '管理面板'

class UserAdminForm(forms.ModelForm):
    """自定义用户管理表单"""
    
    # 自定义密码字段，显示为星号
    password = forms.CharField(
        label='密码',
        required=False,
        widget=forms.PasswordInput(render_value=True, attrs={'value': '********', 'readonly': 'readonly'}),
        help_text='出于安全考虑，密码以加密形式存储。您可以使用下方的密码管理功能修改或重置密码。'
    )
    
    def clean_phone_number(self):
        """验证手机号唯一性"""
        phone_number = self.cleaned_data.get('phone_number')
        # 获取当前编辑的用户实例（如果是编辑操作）
        instance = getattr(self, 'instance', None)
        
        # 检查手机号是否已存在
        if phone_number and User.objects.filter(phone_number=phone_number).exclude(pk=getattr(instance, 'pk', None)).exists():
            raise forms.ValidationError("此手机号已被使用，请使用其他手机号。")
            
        return phone_number
    
    class Meta:
        model = User
        fields = '__all__'

class StaffPasswordChangeForm(PasswordChangeForm):
    """工作人员修改密码表单（需要验证旧密码）"""
    
    def __init__(self, user, *args, **kwargs):
        super().__init__(user, *args, **kwargs)
        self.fields['old_password'].label = "旧密码"
        self.fields['new_password1'].label = "新密码"
        self.fields['new_password2'].label = "确认新密码"
        
    def clean_old_password(self):
        """验证旧密码"""
        old_password = self.cleaned_data.get('old_password')
        if not self.user.check_password(old_password):
            raise forms.ValidationError("旧密码不正确，请重新输入。")
        return old_password

@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """用户管理界面"""
    form = UserAdminForm
    list_display = ('phone_number', 'name', 'is_active', 'start_date', 'end_date', 'updated_by', 'updated_at', 'user_role', 'password_actions')
    list_filter = ('is_active', 'is_staff', 'is_superuser', 'start_date', 'end_date')
    search_fields = ('phone_number', 'name')
    ordering = ('-created_at',)
    
    fieldsets = (
        (None, {'fields': ('phone_number', 'password', 'get_password_info')}),
        ('个人信息', {'fields': ('name', 'start_date', 'end_date')}),
        ('权限', {
            'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions'),
        }),
        ('重要日期', {'fields': ('last_login', 'updated_at')}),
    )
    
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('phone_number', 'name', 'password1', 'password2', 'start_date', 'end_date'),
        }),
    )

    readonly_fields = ('updated_at', 'get_password_info')
    change_password_form = AdminPasswordChangeForm

    def get_urls(self):
        """添加自定义URL"""
        urls = super().get_urls()
        custom_urls = [
            path(
                '<path:object_id>/password/reset/',
                self.admin_site.admin_view(self.reset_password),
                name='users_user_reset_password',
            ),
            path(
                '<path:object_id>/reset-password/',
                self.admin_site.admin_view(self.reset_user_password),
                name='users_user_reset_user_password',
            ),
        ]
        return custom_urls + urls

    def get_password_info(self, obj):
        """密码管理按钮"""
        if not obj or not obj.pk:
            return ""
        
        # 创建密码管理按钮
        change_url = reverse('admin:auth_user_password_change', args=[obj.pk])
        reset_url = reverse('admin:users_user_reset_password', args=[obj.pk])
        
        html = f"""
        <div style="margin-top: 10px;">
            <a href="{change_url}" class="button" style="margin-right: 10px;">修改密码</a>
            <a href="{reset_url}" class="button" 
               onclick="return confirm('确定要重置密码吗？重置后密码将为手机号后6位')">
               重置密码
            </a>
        </div>
        """
        return format_html(html)
    get_password_info.short_description = '密码操作'

    def password_actions(self, obj):
        """显示密码管理按钮，根据用户权限显示不同操作"""
        # 获取当前请求对象
        request = getattr(self, 'request', None)
        
        # 如果没有请求对象，则返回无权限
        if not request:
            return "无权限"
        
        # 判断当前操作用户的权限级别
        current_user = request.user
        is_superuser = current_user.is_superuser
        is_staff = current_user.is_staff and not current_user.is_superuser
        is_normal_user = not (current_user.is_superuser or current_user.is_staff)
        
        # 正确的密码修改URL
        change_url = reverse('admin:auth_user_password_change', args=[obj.pk])
        reset_url = reverse('admin:users_user_reset_password', args=[obj.pk])
        
        # 根据不同用户角色设置不同操作权限
        if is_superuser:
            # 超级用户可以直接修改和重置密码
            html = f"""
            <div>
                <a href="{change_url}" class="button" style="margin-right: 5px;">修改</a>
                <a href="{reset_url}" class="button" 
                   onclick="return confirm('确定要重置密码吗？重置后密码将为手机号后6位')">
                   重置
                </a>
            </div>
            """
        elif is_staff:
            # 工作人员需要验证旧密码才能修改，可以看到修改按钮
            html = f"""
            <div>
                <a href="{change_url}" class="button" style="margin-right: 5px;">修改</a>
            </div>
            """
        else:
            # 普通用户没有权限
            html = "<span>无权限</span>"
            
        return format_html(html)
    password_actions.short_description = '密码操作'

    def user_role(self, obj):
        """显示用户身份"""
        if obj.is_superuser:
            return format_html('<span style="color: red; font-weight: bold;">超级用户</span>')
        elif obj.is_staff:
            return format_html('<span style="color: blue; font-weight: bold;">工作人员</span>')
        else:
            return format_html('<span style="color: green;">普通用户</span>')
    user_role.short_description = '用户身份'

    @method_decorator(csrf_protect)
    def reset_password(self, request, object_id):
        """重置用户密码"""
        try:
            user = self.get_object(request, object_id)
            
            # 检查权限
            if not self.has_change_permission(request, user):
                messages.error(request, '您没有权限重置此用户的密码')
                return redirect('admin:users_user_changelist')
                
            # 超级用户可以重置所有用户的密码
            # 工作人员只能重置普通用户的密码
            if not request.user.is_superuser and (user.is_superuser or user.is_staff):
                messages.error(request, '您没有权限重置管理员或工作人员的密码')
                return redirect('admin:users_user_changelist')
                
            # 生成默认密码（手机号后6位）
            default_password = user.phone_number[-6:]
            user.set_password(default_password)
            user.save()
            
            messages.success(request, f'已成功重置用户 {user.name} 的密码为手机号后6位')
            return redirect('admin:users_user_changelist')
        except Exception as e:
            messages.error(request, f'重置密码时发生错误: {str(e)}')
            return redirect('admin:users_user_changelist')

    @method_decorator(csrf_protect)
    def reset_user_password(self, request, object_id):
        """从用户详情页重置密码"""
        try:
            user = self.get_object(request, object_id)
            
            # 检查权限
            if not self.has_change_permission(request, user):
                messages.error(request, '您没有权限重置此用户的密码')
                return redirect(request.path.replace('/reset-password/', ''))
                
            # 超级用户可以重置所有用户的密码
            # 工作人员只能重置普通用户的密码
            if not request.user.is_superuser and (user.is_superuser or user.is_staff):
                messages.error(request, '您没有权限重置管理员或工作人员的密码')
                return redirect(request.path.replace('/reset-password/', ''))
                
            # 生成默认密码（手机号后6位）
            default_password = user.phone_number[-6:]
            user.set_password(default_password)
            user.save()
            
            messages.success(request, f'已成功重置用户 {user.name} 的密码为手机号后6位')
            return redirect(request.path.replace('/reset-password/', ''))
        except Exception as e:
            logger.error(f"重置密码时发生错误: {str(e)}")
            messages.error(request, f'重置密码时发生错误: {str(e)}')
            return redirect(request.path.replace('/reset-password/', ''))

    def has_module_permission(self, request):
        """控制是否可以访问用户管理模块"""
        # 只有超级用户和工作人员可以访问
        return request.user.is_active and (request.user.is_superuser or request.user.is_staff)

    def has_view_permission(self, request, obj=None):
        """控制查看权限"""
        if not request.user.is_active:
            return False
        # 超级用户可以查看所有用户
        if request.user.is_superuser:
            return True
        # 工作人员只能查看普通用户
        if request.user.is_staff and obj and not (obj.is_superuser or obj.is_staff):
            return True
        # 工作人员可以查看用户列表
        if request.user.is_staff and obj is None:
            return True
        return False

    def has_change_permission(self, request, obj=None):
        """判断是否有修改权限"""
        # 基础权限检查
        has_perm = super().has_change_permission(request, obj)
        
        # 如果没有基础权限，直接返回False
        if not has_perm:
            return False
            
        # 如果是密码修改页面
        if request.path.endswith('password/'):
            # 超级用户可以修改任何用户的密码
            if request.user.is_superuser:
                return True
                
            # 工作人员只能修改普通用户的密码
            if request.user.is_staff and obj and not (obj.is_superuser or obj.is_staff):
                return True
                
            # 普通用户无权修改密码
            return False
        
        # 其他类型的修改，使用默认权限规则
        return has_perm

    def has_delete_permission(self, request, obj=None):
        """控制删除权限"""
        if not request.user.is_active:
            return False
        # 只有超级用户可以删除用户
        return request.user.is_superuser

    def has_add_permission(self, request):
        """控制添加权限"""
        if not request.user.is_active:
            return False
        # 超级用户和工作人员可以添加用户
        return request.user.is_superuser or request.user.is_staff

    def get_queryset(self, request):
        """根据用户权限过滤查询集"""
        qs = super().get_queryset(request)
        # 超级用户可以看到所有用户
        if request.user.is_superuser:
            return qs
        # 工作人员只能看到普通用户
        if request.user.is_staff:
            return qs.filter(is_superuser=False, is_staff=False)
        return qs.none()

    def save_model(self, request, obj, form, change):
        """保存用户时设置创建者和更新者"""
        if not change:  # 如果是新建用户
            obj.created_by = request.user
            # 确保设置username为phone_number
            obj.username = obj.phone_number
        obj.updated_by = request.user
        
        # 如果是工作人员创建用户，确保不会创建超级用户或工作人员
        if not request.user.is_superuser and request.user.is_staff:
            obj.is_superuser = False
            obj.is_staff = False
            
        super().save_model(request, obj, form, change)

    def get_form(self, request, obj=None, **kwargs):
        """重写get_form方法，根据用户角色返回不同的密码修改表单"""
        # 保存请求对象，以便在其他方法中使用
        self.request = request
        
        # 处理密码修改表单
        if request.path.endswith('password/'):
            if request.user.is_superuser:
                # 超级用户使用管理员密码修改表单（不需要旧密码）
                kwargs['form'] = AdminPasswordChangeForm
            else:
                # 普通用户和工作人员使用需要验证旧密码的表单
                kwargs['form'] = StaffPasswordChangeForm
        return super().get_form(request, obj, **kwargs)
        
    def changelist_view(self, request, extra_context=None):
        """保存请求对象，以便在列表视图中使用"""
        self.request = request
        return super().changelist_view(request, extra_context)
