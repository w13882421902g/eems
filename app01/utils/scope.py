"""
分级数据范围工具（权限核心，对照参考仓库 app01/utils/scope.py 移植）

规则：
    超级管理员（super）：看全部功能、全部数据
    部门管理员（dept）：只看自己部门的数据，可在本部门范围内维护
    普通员工（self）  ：只看自己的数据（自己的档案 / 考勤 / 薪资 / 任务）

所有列表页、AJAX 接口、AI 数据点评都统一调用这里的函数，
避免“页面菜单藏起来了但接口还能查到别人数据”的越权问题。
"""
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import render

from app01.models import (
    User, Employee, Department, Attendance, Salary, Task, Notice,
)

# 三种数据范围
SUPER = "super"
DEPT = "dept"
SELF = "self"

# 角色名称（与 init_data / demo_data 初始化保持一致）
SUPER_ROLE_TITLE = "超级管理员"
DEPT_ROLE_TITLE = "部门管理员"

SCOPE_LABEL = {
    SUPER: "超级管理员 · 可见全部数据",
    DEPT: "部门管理员 · 仅可见本部门数据",
    SELF: "普通员工 · 仅可见本人数据",
}


# ---------------------------------------------------------------------------
# 身份判断
# ---------------------------------------------------------------------------
def is_super_admin(user):
    """是否超级管理员：is_superuser 标记 或 拥有“超级管理员”角色"""
    if not user:
        return False
    if getattr(user, "is_superuser", False):
        return True
    return user.roles.filter(title=SUPER_ROLE_TITLE).exists()


def is_dept_admin(user):
    """是否部门管理员：负责某个部门 或 拥有“部门管理员”角色"""
    if not user:
        return False
    if Department.objects.filter(leader_id=user.id).exists():
        return True
    return user.roles.filter(title=DEPT_ROLE_TITLE).exists()


def scope_of(user):
    """返回当前用户的数据范围：super / dept / self"""
    if not user:
        return SELF
    if is_super_admin(user):
        return SUPER
    if is_dept_admin(user):
        return DEPT
    return SELF


def can_manage(user):
    """是否具备维护（增删改）权限：超级管理员、部门管理员"""
    return scope_of(user) in (SUPER, DEPT)


def scope_label(user):
    """当前用户数据范围的中文说明，直接用于页面展示"""
    return SCOPE_LABEL.get(scope_of(user), SCOPE_LABEL[SELF])


# ---------------------------------------------------------------------------
# 超级管理员名额保护（系统必须始终保留至少 1 个超级管理员）
# ---------------------------------------------------------------------------
def super_admin_queryset():
    """所有有效（启用状态）的超级管理员：is_superuser 标记 或 拥有超级管理员角色"""
    return User.objects.filter(
        Q(is_superuser=True) | Q(roles__title=SUPER_ROLE_TITLE),
        is_active=True,
    ).distinct()


def super_admin_count():
    """当前超级管理员人数"""
    return super_admin_queryset().count()


def is_last_super_admin(user):
    """该用户是否是系统里最后一个（且在用的）超级管理员"""
    if not user or not getattr(user, "is_active", False):
        return False
    if not is_super_admin(user):
        return False
    return super_admin_count() <= 1


# ---------------------------------------------------------------------------
# 当前用户的“自己”
# ---------------------------------------------------------------------------
def my_employee(user):
    """当前登录用户对应的员工档案"""
    if not user:
        return None
    # 1) 优先用绑定的登录账号
    employee = Employee.objects.select_related("depart").filter(user_id=user.id).first()
    if employee:
        return employee
    # 2) 兼容历史数据：没有绑定账号时按姓名兜底匹配
    return Employee.objects.select_related("depart").filter(name=user.username).first()


def my_departments(user):
    """当前用户负责的部门"""
    if not user:
        return Department.objects.none()
    return Department.objects.filter(leader_id=user.id)


def my_department_ids(user):
    """当前部门管理员的数据范围部门 ID 列表"""
    ids = set(my_departments(user).values_list("id", flat=True))
    # 部门管理员本身也是员工，把自己档案所在部门一并纳入
    employee = my_employee(user)
    if employee and employee.depart_id:
        ids.add(employee.depart_id)
    return list(ids)


# ---------------------------------------------------------------------------
# 各业务表的数据范围过滤
# ---------------------------------------------------------------------------
def scope_employees(user):
    """员工列表数据范围"""
    queryset = Employee.objects.select_related("depart")
    current = scope_of(user)
    if current == SUPER:
        return queryset
    if current == DEPT:
        return queryset.filter(depart_id__in=my_department_ids(user))
    employee = my_employee(user)
    if employee:
        return queryset.filter(id=employee.id)
    return queryset.none()


def scope_attendance(user):
    """考勤数据范围"""
    queryset = Attendance.objects.select_related("employee", "employee__depart")
    current = scope_of(user)
    if current == SUPER:
        return queryset
    if current == DEPT:
        return queryset.filter(employee__depart_id__in=my_department_ids(user))
    employee = my_employee(user)
    if employee:
        return queryset.filter(employee_id=employee.id)
    return queryset.none()


def scope_salary(user):
    """薪资数据范围"""
    queryset = Salary.objects.select_related("employee", "employee__depart")
    current = scope_of(user)
    if current == SUPER:
        return queryset
    if current == DEPT:
        return queryset.filter(employee__depart_id__in=my_department_ids(user))
    employee = my_employee(user)
    if employee:
        return queryset.filter(employee_id=employee.id)
    return queryset.none()


def scope_tasks(user):
    """任务数据范围：任务的负责人必须在自己的可见范围内"""
    queryset = Task.objects.select_related("leader")
    current = scope_of(user)
    if current == SUPER:
        return queryset
    if current == DEPT:
        dept_ids = my_department_ids(user)
        member_ids = set(
            Employee.objects.filter(
                depart_id__in=dept_ids, user__isnull=False
            ).values_list("user_id", flat=True)
        )
        member_ids.add(user.id)
        return queryset.filter(leader_id__in=member_ids)
    return queryset.filter(leader_id=user.id)


def scope_users(user):
    """可选“负责人”的用户范围（任务负责人、部门负责人下拉框）"""
    queryset = User.objects.all()
    current = scope_of(user)
    if current == SUPER:
        return queryset
    if current == DEPT:
        dept_ids = my_department_ids(user)
        return queryset.filter(
            Q(employee__depart_id__in=dept_ids) | Q(id=user.id)
        ).distinct()
    return queryset.filter(id=user.id)


def scope_departments(user):
    """部门数据范围"""
    queryset = Department.objects.select_related("leader")
    current = scope_of(user)
    if current == SUPER:
        return queryset
    if current == DEPT:
        return queryset.filter(id__in=my_department_ids(user))
    employee = my_employee(user)
    if employee and employee.depart_id:
        return queryset.filter(id=employee.depart_id)
    return queryset.none()


def scope_notices(user):
    """公告属于全员信息，所有人可见"""
    return Notice.objects.select_related("publisher")


# ---------------------------------------------------------------------------
# 越权访问统一拦截页
# ---------------------------------------------------------------------------
def deny(request, message="你没有权限访问该功能"):
    """返回 403 友好提示页（AJAX 请求返回 JSON）"""
    payload = {"status": False, "msg": message}
    is_ajax = request.headers.get("x-requested-with") == "XMLHttpRequest"
    is_ai_post = request.path.startswith("/ai/") and request.method == "POST"
    if is_ajax or is_ai_post:
        return JsonResponse(payload)
    return render(request, "app01/no_permission.html", {"message": message}, status=403)


def require_super(request):
    """仅超级管理员可用的功能：通过返回 None，否则返回拒绝响应"""
    if is_super_admin(getattr(request, "current_user", None)):
        return None
    return deny(request, "该功能仅超级管理员可用")
