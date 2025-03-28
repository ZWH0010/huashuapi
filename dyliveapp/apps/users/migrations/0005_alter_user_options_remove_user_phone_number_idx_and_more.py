# Generated by Django 4.2.19 on 2025-03-06 06:16

import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0004_alter_user_phone_number'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='user',
            options={'ordering': ['-created_at'], 'verbose_name': '前端用户', 'verbose_name_plural': '前端用户'},
        ),
        migrations.RemoveIndex(
            model_name='user',
            name='phone_number_idx',
        ),
        migrations.RemoveIndex(
            model_name='user',
            name='name_idx',
        ),
        migrations.RemoveIndex(
            model_name='user',
            name='validity_period_idx',
        ),
        migrations.AlterField(
            model_name='user',
            name='created_at',
            field=models.DateTimeField(auto_now_add=True, verbose_name='创建时间'),
        ),
        migrations.AlterField(
            model_name='user',
            name='phone_number',
            field=models.CharField(help_text='用户手机号，用于登录', max_length=11, unique=True, validators=[django.core.validators.RegexValidator(message='请输入有效的11位手机号', regex='^1[3-9]\\d{9}$')], verbose_name='手机号'),
        ),
    ]
