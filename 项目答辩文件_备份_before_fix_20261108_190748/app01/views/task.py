"""
任务管理视图（AJAX）
"""
from django.http import JsonResponse
from django.shortcuts import render, redirect
from django.views.decorators.csrf import csrf_exempt
from app01.models import Task, User
from app01.forms import TaskModelForm


def task_list(request):
    """任务列表页面"""
    queryset = Task.objects.all().select_related("leader")
    leader_list = User.objects.all()
    return render(request, "app01/task_list.html", {
        "task_list": queryset,
        "leader_list": leader_list
    })


@csrf_exempt
def task_add_ajax(request):
    """AJAX提交任务，返回JSON"""
    if request.method != "POST":
        return JsonResponse({"status": False, "msg": "请求方式错误"})

    form = TaskModelForm(data=request.POST)
    if form.is_valid():
        form.save()
        # 成功返回
        return JsonResponse({"status": True, "msg": "任务创建成功"})

    # 校验失败，收集错误信息返回
    errors = {field: err_list[0] for field, err_list in form.errors.items()}
    return JsonResponse({"status": False, "errors": errors})


def task_delete(request, pk):
    """删除任务"""
    Task.objects.filter(id=pk).delete()
    return redirect("/task/list/")
