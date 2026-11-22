"""
公告管理视图

功能：
- 列表：标题搜索 + 分页（模型 Meta 已定义“置顶优先、时间倒序”）；
- 发布：发布人取当前登录用户，发布时间由 auto_now_add 自动写入；
- 置顶：POST 切换状态，不需要单独的表单页面；
- 删除：POST + CSRF 保护。
"""
from django.shortcuts import render, redirect
from django.views.decorators.http import require_POST
from django.core.paginator import Paginator
from app01.models import Notice, User
from app01.forms import NoticeModelForm
from app01.utils.scope import can_manage, deny


def notice_list(request):
    """公告列表（搜索、分页；公告全员可见）"""
    user = getattr(request, "current_user", None)
    keyword = request.GET.get("keyword", "")
    # select_related("publisher") 避免模板里 notice.publisher.username 触发 N+1 查询
    queryset = Notice.objects.all().select_related("publisher")
    if keyword:
        queryset = queryset.filter(title__contains=keyword)

    # 每页 8 条；排序由模型 Meta.ordering 统一控制
    paginator = Paginator(queryset, 8)
    page_obj = paginator.get_page(request.GET.get("page", 1))
    return render(request, "app01/notice_list.html", {
        "page_obj": page_obj,
        "keyword": keyword,
        # 普通员工只读，不能发布/编辑/删除公告
        "can_manage": can_manage(user),
    })


def notice_add(request):
    """发布公告（超级管理员、部门管理员）"""
    user = getattr(request, "current_user", None)
    if not can_manage(user):
        return deny(request, "普通员工只能查看公告，不能发布")
    if request.method == "GET":
        form = NoticeModelForm()
        return render(request, "app01/notice_change.html", {"form": form})

    form = NoticeModelForm(data=request.POST)
    if form.is_valid():
        notice = form.save(commit=False)
        # 发布人不让前端选，直接取当前登录用户，防止伪造发布人
        notice.publisher_id = request.session.get("user_id")
        notice.save()
        return redirect("/notice/list/")
    return render(request, "app01/notice_change.html", {"form": form})


def notice_edit(request, pk):
    """编辑公告（发布人和发布时间保持不变）"""
    user = getattr(request, "current_user", None)
    if not can_manage(user):
        return deny(request, "普通员工不能编辑公告")
    notice = Notice.objects.filter(id=pk).first()
    if not notice:
        return redirect("/notice/list/")

    if request.method == "GET":
        form = NoticeModelForm(instance=notice)
        return render(request, "app01/notice_change.html", {"form": form})

    form = NoticeModelForm(data=request.POST, instance=notice)
    if form.is_valid():
        form.save()
        return redirect("/notice/list/")
    return render(request, "app01/notice_change.html", {"form": form})


@require_POST
def notice_top(request, pk):
    """切换置顶状态：点一下置顶，再点一下取消"""
    user = getattr(request, "current_user", None)
    if not can_manage(user):
        return deny(request, "普通员工不能操作置顶")
    notice = Notice.objects.filter(id=pk).first()
    if notice:
        notice.is_top = not notice.is_top
        notice.save()
    return redirect("/notice/list/")


@require_POST
def notice_delete(request, pk):
    """删除公告（只接受 POST）"""
    user = getattr(request, "current_user", None)
    if not can_manage(user):
        return deny(request, "普通员工不能删除公告")
    Notice.objects.filter(id=pk).delete()
    return redirect("/notice/list/")
