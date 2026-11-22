"""
角色管理视图（RBAC 的“角色-权限”分配入口）

权限控制：整个模块都加了 @superuser_required，
普通用户即使知道 URL 也会被返回 403，避免越权改角色。
"""
from django.shortcuts import render, redirect
from django.views.decorators.http import require_POST
from app01.models import Role
from app01.forms import RoleModelForm
from app01.utils.perm import superuser_required


@superuser_required
def role_list(request):
    """角色列表：prefetch_related 一次性取出每个角色的权限，避免模板循环查库"""
    queryset = Role.objects.all().prefetch_related("permissions")
    return render(request, "app01/role_list.html", {"role_list": queryset})


@superuser_required
def role_add(request):
    """新建角色（勾选权限）"""
    if request.method == "GET":
        form = RoleModelForm()
        return render(request, "app01/role_change.html", {"form": form})

    form = RoleModelForm(data=request.POST)
    if form.is_valid():
        form.save()   # ModelForm 会自动保存多对多关系（权限勾选）
        return redirect("/role/list/")
    return render(request, "app01/role_change.html", {"form": form})


@superuser_required
def role_edit(request, pk):
    """编辑角色（重新分配权限）"""
    role = Role.objects.filter(id=pk).first()
    if not role:
        return redirect("/role/list/")

    if request.method == "GET":
        form = RoleModelForm(instance=role)
        return render(request, "app01/role_change.html", {"form": form})

    form = RoleModelForm(data=request.POST, instance=role)
    if form.is_valid():
        form.save()
        return redirect("/role/list/")
    return render(request, "app01/role_change.html", {"form": form})


@require_POST
@superuser_required
def role_delete(request, pk):
    """
    删除角色。

    装饰器顺序说明：require_POST 在上、superuser_required 在下，
    请求先被“仅 POST”拦住，再进入超级管理员校验；
    这样可以避免 GET 请求也走一遍权限查询。

    保护规则：角色下还有用户时禁止删除，否则这些账号会失去全部权限定义；
    尤其“超级管理员 / 部门管理员”角色是权限分级的依据，不能随意删。
    """
    role = Role.objects.filter(id=pk).first()
    if not role:
        return redirect("/role/list/")
    if role.users.exists():
        return deny(request, "该角色下还有 %d 个用户，请先调整用户角色后再删除" % role.users.count())
    role.delete()
    return redirect("/role/list/")
