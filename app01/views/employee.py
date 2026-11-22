"""
员工管理视图（带搜索、部门筛选、分页和文件上传）

路由：
    GET  /employee/list/            列表（支持 ?keyword=&depart_id=&page=）
    GET/POST /employee/add/          新建（POST 带 multipart 上传头像）
    GET/POST /employee/edit/<pk>/    编辑
    POST /employee/delete/<pk>/      删除
"""
from django.shortcuts import render, redirect
from django.views.decorators.http import require_POST
from django.core.paginator import Paginator
from app01.models import Employee, Department
from app01.forms import EmployeeModelForm
from app01.utils.scope import (
    can_manage, deny, my_department_ids, scope_departments, scope_employees,
    scope_of, scope_users, SELF, SUPER,
)


def employee_list(request):
    """
    员工列表（搜索、部门筛选、分页）

    关键点：
    - 数据先按当前账号的数据范围过滤：超管看全部，部门管理员看本部门，员工只看自己；
    - select_related("depart") 消除模板里 emp.depart.title 的 N+1 查询；
    - order_by("id") 显式排序：如果不排序，数据库分页顺序不稳定，
      可能出现同一条记录在两页重复、或有记录永远查不到；
    - 分页参数统一用 Paginator.get_page()，页码非法（0、负数、字母）时自动回退到第 1 页。
    """
    user = getattr(request, "current_user", None)
    scope = scope_of(user)
    keyword = request.GET.get("keyword", "")
    depart_id = request.GET.get("depart_id", "").strip()

    # 先套权限范围，再做搜索/筛选，顺序不能反：否则会把无权限的人筛出来
    queryset = scope_employees(user).order_by("id")
    # 姓名模糊搜索：__contains 会翻译成 SQL 的 LIKE '%关键词%'
    if keyword:
        queryset = queryset.filter(name__contains=keyword)
    # 部门筛选：先判断是否为数字，非法参数直接忽略，避免 int() 抛异常
    if depart_id.isdigit():
        queryset = queryset.filter(depart_id=int(depart_id))

    # 每页 8 条
    paginator = Paginator(queryset, 8)
    page_obj = paginator.get_page(request.GET.get("page", 1))

    return render(request, "app01/employee_list.html", {
        "page_obj": page_obj,
        # 部门下拉框也只给当前账号可见的部门
        "depart_list": scope_departments(user),
        # 回传给模板，分页链接要带上当前搜索条件，否则翻页后筛选条件会丢失
        "keyword": keyword,
        "depart_id": int(depart_id) if depart_id.isdigit() else "",
        # 普通员工只读；模板据此隐藏“新增 / 编辑 / 删除”按钮
        "can_manage": can_manage(user),
        "is_super_scope": scope == SUPER,
        "is_self_scope": scope == SELF,
    })


def _limit_form(form, user):
    """把表单里的部门、登录账号下拉框限制在当前账号的数据范围内"""
    if "depart" in form.fields:
        form.fields["depart"].queryset = scope_departments(user)
    if "user" in form.fields:
        form.fields["user"].queryset = scope_users(user)
    return form


def employee_add(request):
    """新建员工（超级管理员、部门管理员；员工本人无权新增）"""
    user = getattr(request, "current_user", None)
    if not can_manage(user):
        return deny(request, "普通员工没有新增员工档案的权限")

    if request.method == "GET":
        form = _limit_form(EmployeeModelForm(), user)
        return render(request, "app01/employee_change.html", {"form": form})

    # 带文件上传的表单必须同时传 request.POST 和 request.FILES
    form = _limit_form(EmployeeModelForm(data=request.POST, files=request.FILES), user)
    if form.is_valid():
        employee = form.save(commit=False)
        # 部门管理员只能在本人负责的部门里新增，防止通过改表单把员工挂到其他部门
        if scope_of(user) != SUPER and employee.depart_id not in my_department_ids(user):
            return deny(request, "你只能在本部门范围内新增员工")
        employee.save()
        return redirect("/employee/list/")
    # 校验失败：把带错误信息的 form 回传模板，页面会逐字段显示错误
    return render(request, "app01/employee_change.html", {"form": form})


def employee_edit(request, pk):
    """编辑员工（需具备维护权限，且目标员工必须在自己的数据范围内）"""
    user = getattr(request, "current_user", None)
    if not can_manage(user):
        return deny(request, "普通员工只能查看本人档案，不能修改")

    employee = scope_employees(user).filter(id=pk).first()
    if not employee:
        return deny(request, "该员工不在你的数据范围内，无法编辑")

    if request.method == "GET":
        # instance=employee：表单自动回填该员工的现有数据
        form = _limit_form(EmployeeModelForm(instance=employee), user)
        return render(request, "app01/employee_change.html", {"form": form})

    # 编辑时同样要传 files，否则选择新头像不会被接收
    form = _limit_form(EmployeeModelForm(data=request.POST, files=request.FILES, instance=employee), user)
    if form.is_valid():
        form.save()
        return redirect("/employee/list/")
    return render(request, "app01/employee_change.html", {"form": form})


@require_POST
def employee_delete(request, pk):
    """删除员工（只接受 POST；且必须在自己的数据范围内）"""
    user = getattr(request, "current_user", None)
    if not can_manage(user):
        return deny(request, "普通员工没有删除员工档案的权限")
    target = scope_employees(user).filter(id=pk).first()
    if not target:
        return deny(request, "该员工不在你的数据范围内，无法删除")
    # 先解除登录账号绑定，避免删除档案后账号还被当作“已绑定”
    target.user = None
    target.save(update_fields=["user"])
    target.delete()
    return redirect("/employee/list/")
