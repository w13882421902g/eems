"""
部门管理视图
"""
from django.shortcuts import render, redirect
from app01.models import Department, User


def department_list(request):
    """部门列表"""
    # select_related优化关联查询，消除N+1
    queryset = Department.objects.all().select_related("leader")
    return render(request, "app01/department_list.html", {"depart_list": queryset})


def department_add(request):
    """新建部门"""
    if request.method == "GET":
        # 用户列表用于选择负责人
        user_list = User.objects.all()
        return render(request, "app01/department_change.html", {"user_list": user_list})

    # POST：获取数据并创建
    title = request.POST.get("title", "")
    leader_id = request.POST.get("leader_id")
    Department.objects.create(
        title=title,
        leader_id=leader_id if leader_id else None
    )
    return redirect("/depart/list/")


def department_edit(request, pk):
    """编辑部门"""
    depart = Department.objects.filter(id=pk).first()
    if not depart:
        return redirect("/depart/list/")

    if request.method == "GET":
        user_list = User.objects.all()
        return render(request, "app01/department_change.html", {
            "depart": depart, "user_list": user_list
        })

    # POST：更新数据
    depart.title = request.POST.get("title", "")
    leader_id = request.POST.get("leader_id")
    depart.leader_id = leader_id if leader_id else None
    depart.save()
    return redirect("/depart/list/")


def department_delete(request, pk):
    """删除部门"""
    Department.objects.filter(id=pk).delete()
    return redirect("/depart/list/")
