"""
用户管理视图（系统级功能）

安全要点：
1. 整个模块加 @superuser_required，普通用户访问/提交都会得到 403；
2. 新增用户不接收明文密码，统一用 set_password("123456") 生成哈希；
3. 重置密码、删除用户都只允许 POST，并校验 CSRF。
"""
from django.shortcuts import render, redirect
from django.views.decorators.http import require_POST
from app01.models import User, Role
from app01.forms import UserModelForm
from app01.utils.perm import superuser_required
from app01.utils.scope import SUPER_ROLE_TITLE, deny, is_last_super_admin


@superuser_required
def user_list(request):
    """用户列表：prefetch_related 预取角色，避免 N+1 查询"""
    queryset = User.objects.all().prefetch_related("roles")
    return render(request, "app01/user_manage_list.html", {"user_list": queryset})


@superuser_required
def user_add(request):
    """新增用户"""
    if request.method == "GET":
        form = UserModelForm()
        return render(request, "app01/user_manage_change.html", {"form": form})

    form = UserModelForm(data=request.POST)
    if form.is_valid():
        user = form.save(commit=False)
        # 密码统一由后端设置：set_password 会做加盐哈希，数据库不存明文
        user.set_password("123456")
        user.save()
        # 上面的 commit=False 只保存了普通字段，多对多角色必须再调用 save_m2m 保存
        form.save_m2m()
        return redirect("/user_manage/list/")
    return render(request, "app01/user_manage_change.html", {"form": form})


@superuser_required
def user_edit(request, pk):
    """编辑用户（只改基本信息和角色，不改密码）"""
    user = User.objects.filter(id=pk).first()
    if not user:
        return redirect("/user_manage/list/")

    if request.method == "GET":
        form = UserModelForm(instance=user)
        return render(request, "app01/user_manage_change.html", {"form": form})

    form = UserModelForm(data=request.POST, instance=user)
    if form.is_valid():
        # 最后一个超管保护：不能把系统里唯一的超级管理员取消超管身份或停用
        if is_last_super_admin(user):
            keeps_flag = form.cleaned_data.get("is_superuser")
            keeps_role = any(
                role.title == SUPER_ROLE_TITLE for role in form.cleaned_data.get("roles") or []
            )
            if not keeps_flag and not keeps_role:
                return deny(request, "系统必须保留至少一名超级管理员，不能取消最后一个超管")
            if not form.cleaned_data.get("is_active"):
                return deny(request, "系统必须保留至少一名启用状态的超级管理员，不能停用最后一个超管")
        form.save()
        return redirect("/user_manage/list/")
    return render(request, "app01/user_manage_change.html", {"form": form})


@require_POST
@superuser_required
def user_reset_pwd(request, pk):
    """重置密码为默认口令 123456（POST 提交，防止 GET 触发状态变更）"""
    user = User.objects.filter(id=pk).first()
    if user:
        user.set_password("123456")
        user.save()
    return redirect("/user_manage/list/")


@require_POST
@superuser_required
def user_delete(request, pk):
    """删除用户（只接受 POST）；最后一个超管不能删除"""
    user = User.objects.filter(id=pk).first()
    if user and is_last_super_admin(user):
        return deny(request, "系统必须保留至少一名超级管理员，不能删除最后一个超管")
    User.objects.filter(id=pk).delete()
    return redirect("/user_manage/list/")
