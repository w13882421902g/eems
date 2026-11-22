"""
任务管理视图（AJAX 异步交互）

和普通 CRUD 的区别：
- 新建任务不走整页表单提交，而是前端 jQuery AJAX 发 POST，后端返回 JSON；
- 校验失败时把字段错误按 {字段名: 错误信息} 返回，前端把错误写到对应输入框下方；
- 删除仍然走普通表单 POST（带 CSRF），保证操作可预期。
"""
from django.http import JsonResponse
from django.shortcuts import render, redirect
from django.views.decorators.http import require_POST
from app01.models import Task, User
from app01.forms import TaskModelForm
from app01.utils.pagination import Pagination
from app01.utils.scope import can_manage, deny, scope_tasks, scope_users


def _limit_form(form, user):
    """任务负责人下拉框只给数据范围内的人"""
    if "leader" in form.fields:
        form.fields["leader"].queryset = scope_users(user)
    return form


def task_list(request):
    """
    任务列表页面：左侧新建表单 + 右侧任务表格（分页）。

    分页要点：
    - 必须显式 order_by，否则数据库返回顺序不稳定，翻页会出现重复/漏记录；
    - Pagination 内部用 QuerySet 切片，SQL 只取当前页（LIMIT/OFFSET）；
    - 任务按负责人归属过滤：超管看全部，部门管理员看本部门成员，员工只看自己的。
    """
    user = getattr(request, "current_user", None)
    queryset = scope_tasks(user).order_by("-id")
    page_object = Pagination(request, queryset, page_size=10)

    return render(request, "app01/task_list.html", {
        "page_queryset": page_object.page_queryset,
        "page_string": page_object.html(),
        "total_count": page_object.total_count,
        "leader_list": scope_users(user),
        "can_manage": can_manage(user),
    })


def task_add_ajax(request):
    """
    AJAX 提交任务，返回 JSON。

    返回结构约定：
    - 成功：{"status": true, "msg": "任务创建成功"}
    - 校验失败：{"status": false, "errors": {"title": "标题至少2个字符", ...}}
    - 方法不对：{"status": false, "msg": "请求方式错误"}
    """
    if request.method != "POST":
        return JsonResponse({"status": False, "msg": "请求方式错误"})

    user = getattr(request, "current_user", None)
    # 普通员工只能查看自己的任务，不能新建任务给人派活
    if not can_manage(user):
        return JsonResponse({"status": False, "msg": "普通员工没有新建任务的权限"})

    form = _limit_form(TaskModelForm(data=request.POST), user)
    if form.is_valid():
        form.save()
        return JsonResponse({"status": True, "msg": "任务创建成功"})

    # 校验失败：form.errors 的值是列表，这里只取每个字段的第一条错误，结构更简单
    errors = {field: err_list[0] for field, err_list in form.errors.items()}
    return JsonResponse({"status": False, "errors": errors})


@require_POST
def task_delete(request, pk):
    """删除任务（普通表单 POST，不是 AJAX）；普通员工无权删除"""
    user = getattr(request, "current_user", None)
    if not can_manage(user):
        return deny(request, "普通员工没有删除任务的权限")
    if not scope_tasks(user).filter(id=pk).exists():
        return deny(request, "该任务不在你的数据范围内")
    Task.objects.filter(id=pk).delete()
    return redirect("/task/list/")
