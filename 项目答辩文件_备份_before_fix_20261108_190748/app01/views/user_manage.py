"""
用户管理视图
"""
from django.shortcuts import render, redirect
from app01.models import User, Role
from app01.forms import UserModelForm


def user_list(request):
    """用户列表"""
    queryset = User.objects.all().prefetch_related("roles")
    return render(request, "app01/user_manage_list.html", {"user_list": queryset})


def user_add(request):
    """新增用户"""
    if request.method == "GET":
        form = UserModelForm()
        return render(request, "app01/user_manage_change.html", {"form": form})

    form = UserModelForm(data=request.POST)
    if form.is_valid():
        user = form.save(commit=False)
        # 新增用户设置默认密码，用安全哈希
        user.set_password("123456")
        user.save()
        form.save_m2m()
        return redirect("/user_manage/list/")
    return render(request, "app01/user_manage_change.html", {"form": form})


def user_edit(request, pk):
    """编辑用户（只改信息和角色，不改密码）"""
    user = User.objects.filter(id=pk).first()
    if not user:
        return redirect("/user_manage/list/")

    if request.method == "GET":
        form = UserModelForm(instance=user)
        return render(request, "app01/user_manage_change.html", {"form": form})

    form = UserModelForm(data=request.POST, instance=user)
    if form.is_valid():
        form.save()
        return redirect("/user_manage/list/")
    return render(request, "app01/user_manage_change.html", {"form": form})


def user_reset_pwd(request, pk):
    """重置密码为123456"""
    user = User.objects.filter(id=pk).first()
    if user:
        user.set_password("123456")
        user.save()
    return redirect("/user_manage/list/")


def user_delete(request, pk):
    """删除用户"""
    User.objects.filter(id=pk).delete()
    return redirect("/user_manage/list/")
