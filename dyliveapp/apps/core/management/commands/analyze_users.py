from django.core.management.base import BaseCommand
from django.utils import timezone
from apps.core.monitoring.user_analytics import UserAnalytics
from typing import Any, Optional
import json
from datetime import datetime

class Command(BaseCommand):
    help = '用户行为分析管理命令'

    def add_arguments(self, parser):
        parser.add_argument(
            '--action',
            choices=['summary', 'segments', 'active', 'popular', 'clear'],
            default='summary',
            help='要执行的分析操作'
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=10,
            help='返回结果的数量限制'
        )
        parser.add_argument(
            '--days',
            type=int,
            help='数据保留天数（用于clear操作）'
        )
        parser.add_argument(
            '--output',
            help='输出文件路径'
        )

    def handle(self, *args: Any, **options: Any) -> Optional[str]:
        analytics = UserAnalytics.get_instance()
        action = options['action']
        limit = options['limit']
        days = options.get('days')
        output_file = options.get('output')

        result = None

        if action == 'summary':
            result = analytics.get_activity_summary()
            self.stdout.write(self.style.SUCCESS('活动摘要:'))
            self.print_dict(result)

        elif action == 'segments':
            result = analytics.get_user_segments()
            self.stdout.write(self.style.SUCCESS('用户分群:'))
            for segment, users in result.items():
                self.stdout.write(f'{segment}: {len(users)} 用户')
                if len(users) > 0:
                    self.stdout.write(f'示例用户ID: {users[:5]}')

        elif action == 'active':
            result = analytics.get_most_active_users(limit)
            self.stdout.write(self.style.SUCCESS(f'最活跃的 {limit} 个用户:'))
            for user in result:
                self.stdout.write(
                    f"用户 {user['user_id']}: "
                    f"{user['session_count']} 个会话, "
                    f"最后活跃: {user['last_active']}"
                )

        elif action == 'popular':
            result = analytics.get_popular_actions()
            self.stdout.write(self.style.SUCCESS('最受欢迎的操作:'))
            for action, count in list(result.items())[:limit]:
                self.stdout.write(f'{action}: {count} 次')

        elif action == 'clear':
            analytics.clear_old_data(days)
            self.stdout.write(
                self.style.SUCCESS(
                    f'已清理 {days if days else analytics.DEFAULT_RETENTION_DAYS} 天前的数据'
                )
            )

        # 如果指定了输出文件，将结果保存到文件
        if output_file and result:
            self.save_to_file(result, output_file)
            self.stdout.write(
                self.style.SUCCESS(f'结果已保存到: {output_file}')
            )

    def print_dict(self, data: dict, indent: int = 0) -> None:
        """格式化打印字典数据"""
        for key, value in data.items():
            if isinstance(value, dict):
                self.stdout.write('  ' * indent + f'{key}:')
                self.print_dict(value, indent + 1)
            else:
                self.stdout.write('  ' * indent + f'{key}: {value}')

    def save_to_file(self, data: Any, filepath: str) -> None:
        """保存结果到文件"""
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                if isinstance(data, dict):
                    json.dump(data, f, ensure_ascii=False, indent=2, default=str)
                else:
                    json.dump(
                        {'data': data},
                        f,
                        ensure_ascii=False,
                        indent=2,
                        default=str
                    )
        except Exception as e:
            self.stderr.write(
                self.style.ERROR(f'保存文件时出错: {str(e)}')
            ) 