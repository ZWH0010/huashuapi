from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from datetime import timedelta, date
import json
import os

User = get_user_model()

class Command(BaseCommand):
    help = '初始化负载测试所需的测试数据'

    def handle(self, *args, **options):
        try:
            # 读取测试数据
            test_data_path = os.path.join('tests', 'load', 'data', 'test_data.json')
            with open(test_data_path, 'r') as f:
                test_data = json.load(f)

            with transaction.atomic():
                # 创建测试用户
                for user_data in test_data['users']:
                    start_date = timezone.now().date()
                    end_date = start_date + timedelta(days=365)  # 一年有效期
                    
                    user, created = User.objects.get_or_create(
                        phone_number=user_data['phone_number'],
                        defaults={
                            'is_active': True,
                            'start_date': start_date,
                            'end_date': end_date,
                            'name': f'测试用户{user_data["phone_number"][-4:]}'
                        }
                    )
                    if created:
                        user.set_password(user_data['password'])
                        user.save()
                        self.stdout.write(
                            self.style.SUCCESS(
                                f'Successfully created test user: {user.phone_number}'
                            )
                        )
                    else:
                        self.stdout.write(
                            self.style.WARNING(
                                f'Test user already exists: {user.phone_number}'
                            )
                        )

            self.stdout.write(
                self.style.SUCCESS('Successfully initialized test data')
            )

        except Exception as e:
            self.stderr.write(
                self.style.ERROR(f'Error initializing test data: {str(e)}')
            ) 