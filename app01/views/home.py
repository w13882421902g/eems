"""
首页门户（对照参考仓库 app01/views/home.py 移植）

作用：按当前登录角色的数据范围展示概览。
答辩时切换三个账号（超级管理员 / 部门管理员 / 普通员工），
首页的“数据范围说明 + 数字”会直接变化，直观证明权限分级生效。
"""
import datetime

from django.db.models import Sum
from django.shortcuts import render

from app01.models import Notice, Order
from app01.utils.scope import (
    SELF, SUPER, can_manage, my_departments, my_employee,
    scope_attendance, scope_employees, scope_label, scope_of, scope_salary,
    scope_tasks, super_admin_count,
)


def home(request):
    """系统首页"""
    user = getattr(request, "current_user", None)
    if not user:
        return render(request, "app01/login.html", {"error": "请先登录"})

    today = datetime.date.today()
    month = today.strftime("%Y-%m")
    employee_qs = scope_employees(user)
    attendance_qs = scope_attendance(user).filter(date__year=today.year)
    salary_qs = scope_salary(user).filter(month=month)
    task_qs = scope_tasks(user)
    scope = scope_of(user)

    cards = {
        "employee_count": employee_qs.count(),
        "attendance_count": attendance_qs.count(),
        "salary_total": salary_qs.aggregate(total=Sum("total"))["total"] or 0,
        "task_count": task_qs.count(),
        "dept_names": "、".join(my_departments(user).values_list("title", flat=True)) or "—",
        "month": month,
    }
    # 超管额外展示全局口径，方便和部门数据对比
    if scope == SUPER:
        cards["super_admin_count"] = super_admin_count()
        cards["order_count"] = Order.objects.count()

    employee = my_employee(user)
    return render(request, "app01/home.html", {
        "cards": cards,
        "scope": scope,
        "scope_label": scope_label(user),
        "can_manage": can_manage(user),
        "employee": employee,
        "notice_list": Notice.objects.all()[:5],
        "is_employee_scope": scope == SELF,
        "today": today,
    })
