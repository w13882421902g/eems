"""
模板上下文处理器（对照参考仓库 app01/context_processors.py 移植）

作用：把“当前登录用户 + 数据范围 + 导航菜单”注入所有模板，
这样导航栏就能按角色自动显示不同功能：
    超级管理员 -> 全部菜单
    部门管理员 -> 本部门相关菜单
    普通员工   -> 只显示“我的”菜单
"""
from django.middleware.csrf import get_token

from app01.utils.scope import (
    SUPER, DEPT, SELF, scope_of, scope_label, can_manage, my_departments, my_employee,
)

# 每个角色的导航项：(标题, 跳转地址, 高亮匹配前缀)
NAV_SUPER = [
    ("首页", "/home/", "/home/"),
    ("部门管理", "/depart/list/", "/depart/"),
    ("员工管理", "/employee/list/", "/employee/"),
    ("考勤管理", "/attendance/list/", "/attendance/"),
    ("薪资管理", "/salary/list/", "/salary/"),
    ("公告管理", "/notice/list/", "/notice/"),
    ("任务管理", "/task/list/", "/task/"),
    ("订单管理", "/order/list/", "/order/"),
    ("数据统计", "/chart/", "/chart/"),
    ("用户管理", "/user_manage/list/", "/user_manage/"),
    ("角色管理", "/role/list/", "/role/"),
    ("智能助手", "/ai/assistant/", "/ai/"),
]
NAV_DEPT = [
    ("首页", "/home/", "/home/"),
    ("我的部门", "/depart/list/", "/depart/"),
    ("员工管理", "/employee/list/", "/employee/"),
    ("考勤管理", "/attendance/list/", "/attendance/"),
    ("薪资管理", "/salary/list/", "/salary/"),
    ("公告管理", "/notice/list/", "/notice/"),
    ("任务管理", "/task/list/", "/task/"),
    ("数据统计", "/chart/", "/chart/"),
    ("智能助手", "/ai/assistant/", "/ai/"),
]
NAV_SELF = [
    ("首页", "/home/", "/home/"),
    ("我的档案", "/employee/list/", "/employee/"),
    ("我的考勤", "/attendance/list/", "/attendance/"),
    ("我的薪资", "/salary/list/", "/salary/"),
    ("公告栏", "/notice/list/", "/notice/"),
    ("我的任务", "/task/list/", "/task/"),
    ("智能助手", "/ai/assistant/", "/ai/"),
]


def nav_context(request):
    """注入导航与权限标识"""
    user = getattr(request, "current_user", None)
    if not user:
        return {}
    scope = scope_of(user)
    if scope == SUPER:
        nav_items = NAV_SUPER
    elif scope == DEPT:
        nav_items = NAV_DEPT
    else:
        nav_items = NAV_SELF
    employee = my_employee(user)
    # 任何页面都保证下发 csrftoken，AI 浮窗才能直接发 POST
    get_token(request)
    return {
        "current_user": user,
        "scope": scope,
        "is_super_scope": scope == SUPER,
        "is_dept_scope": scope == DEPT,
        "is_self_scope": scope == SELF,
        "scope_label": scope_label(user),
        "can_manage": can_manage(user),
        "nav_items": nav_items,
        "my_employee": employee,
        "my_dept_names": "、".join(
            my_departments(user).values_list("title", flat=True)
        ),
    }
