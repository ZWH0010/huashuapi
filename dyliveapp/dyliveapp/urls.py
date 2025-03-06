"""
URL configuration for dyliveapp project.

The `urlpatterns` list routes URLs to views. For more information please see:
    python manage.py test apps.users.testshttps://docs.djangoproject.com/en/5.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from rest_framework_simplejwt.views import TokenRefreshView

urlpatterns = [
    path('admin/', admin.site.urls),  # Django自带的管理后台
    path('api/users/', include('apps.users.urls')),  # 用户API
    path('api/', include('apps.tags.urls')),  # 标签API
    path('api/', include('apps.scripts.urls')),  # 话术API
    path('api/v1/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
