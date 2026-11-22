"""
角色管理视图（RBAC）
"""
from django.shortcuts import render, redirect
from app01.models import Role
from app01.forms import RoleModelForm


def role_list(request):
    """角色列表"""
    queryset = Role.objects.all().prefetch_related("permissions")
    return render(request, "app01/role_list.html", {"role_list": queryset})


def role_add(request):
    """新建角色"""
    if request.method == "GET":
        form = RoleModelForm()
        return render(request, "app01/role_change.html", {"form": form})

    form = RoleModelForm(data=request.POST)
    if form.is_valid():
        form.save()
        return redirect("/role/list/")
    return render(request, "app01/role_change.html", {"form": form})


def role_edit(request, pk):
    """编辑角色（分配权限）"""
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


def role_delete(request, pk):
    """删除角色"""
    Role.objects.filter(id=pk).delete()
    return redirect("/role/list/")
