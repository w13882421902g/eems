"""
管理命令：生成演示任务数据（对照参考仓库 demo_tasks.py 移植）

用途：
    演示分级权限时，需要“不同部门成员手上都有任务”，
    否则任务列表只有管理员的记录，看不出部门管理员与员工视角的差别。

用法：
    python manage.py demo_tasks          # 为有登录账号的员工各生成 1-2 条任务
    python manage.py demo_tasks --count 2
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from app01.models import Employee, Task

TASK_POOL = [
    ("月度考勤汇总", "整理本月考勤异常记录，提交部门负责人复核", 2),
    ("新员工入职材料", "收集身份证、学历证明等入职材料并归档", 3),
    ("招聘渠道复盘", "统计各招聘渠道的简历量与到面率，输出复盘结论", 2),
    ("薪资表核对", "核对本月薪资明细与考勤扣款是否一致", 1),
    ("团建活动筹备", "确定时间地点、预算与参与名单", 4),
]


class Command(BaseCommand):
    help = "生成演示任务数据，让不同部门管理员的任务列表都能看到内容"

    def add_arguments(self, parser):
        parser.add_argument("--count", type=int, default=2, help="每人生成的任务数量（默认 2）")

    def handle(self, *args, **options):
        count = max(1, min(options["count"], len(TASK_POOL)))
        created = 0
        with transaction.atomic():
            for index, employee in enumerate(Employee.objects.select_related("user").filter(user__isnull=False)):
                for offset in range(count):
                    title, detail, level = TASK_POOL[(index + offset) % len(TASK_POOL)]
                    unique_title = f"{title} · {employee.name}"
                    if Task.objects.filter(title=unique_title).exists():
                        continue
                    Task.objects.create(
                        title=unique_title[:64],
                        detail=detail,
                        level=level,
                        leader=employee.user,
                    )
                    created += 1
        self.stdout.write(self.style.SUCCESS(f"完成：新增任务 {created} 条"))
