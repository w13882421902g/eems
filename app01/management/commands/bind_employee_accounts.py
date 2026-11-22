"""
管理命令：把员工档案与登录账号绑定（对照参考仓库 bind_employee_accounts.py 移植）

用途：
    分级权限里的“普通员工只看本人数据”依赖 Employee.user 字段定位“本人”。
    历史数据里的员工没有绑定账号，命令按“员工姓名 = 登录用户名”自动绑定；
    如果系统里还没有对应账号，可用 --create-users 自动创建（默认密码 123456）。

用法：
    python manage.py bind_employee_accounts            # 只绑定已存在的同名账号
    python manage.py bind_employee_accounts --create-users   # 没有账号时自动创建
    python manage.py bind_employee_accounts --dry-run  # 只看结果，不写库
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from app01.models import Employee, User

DEFAULT_PASSWORD = "123456"


class Command(BaseCommand):
    help = "按姓名把员工档案绑定到登录账号，供分级权限判断“本人数据”"

    def add_arguments(self, parser):
        parser.add_argument(
            "--create-users", action="store_true",
            help="员工没有同名账号时自动创建（密码 123456）",
        )
        parser.add_argument(
            "--dry-run", action="store_true",
            help="只输出将要执行的绑定结果，不写数据库",
        )

    def handle(self, *args, **options):
        create_users = options["create_users"]
        dry_run = options["dry_run"]

        bound = 0
        created = 0
        skipped = []
        employees = Employee.objects.select_related("user").order_by("id")

        with transaction.atomic():
            for employee in employees:
                if employee.user_id:
                    skipped.append(f"{employee.name}：已绑定 {employee.user.username}")
                    continue
                account = User.objects.filter(username=employee.name, is_active=True).first()
                if account is None and create_users:
                    account = User.objects.create_user(
                        username=employee.name,
                        password=DEFAULT_PASSWORD,
                        is_active=True,
                    )
                    created += 1
                    self.stdout.write(f"创建账号 {employee.name}（默认密码 {DEFAULT_PASSWORD}）")
                if account is None:
                    skipped.append(f"{employee.name}：没有同名账号")
                    continue
                if Employee.objects.filter(user=account).exclude(id=employee.id).exists():
                    skipped.append(f"{employee.name}：账号 {account.username} 已绑定其他档案")
                    continue
                if not dry_run:
                    employee.user = account
                    employee.save(update_fields=["user"])
                bound += 1
                self.stdout.write(f"绑定 {employee.name} -> {account.username}")

            if dry_run:
                transaction.set_rollback(True)

        self.stdout.write(self.style.SUCCESS(
            f"完成：绑定 {bound} 条，新建账号 {created} 个，跳过 {len(skipped)} 条"
        ))
        for line in skipped:
            self.stdout.write("  " + line)
