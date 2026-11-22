"""
员工管理视图
"""
from django.shortcuts import render, redirect
from django.views.decorators.http import require_POST
from django.core.paginator import Paginator
from app01.models import Employee, Department
from app01.forms import EmployeeModelForm


def employee_list(request):
    """员工列表（搜索、部门筛选、分页）"""
    keyword = request.GET.get("keyword", "")
    depart_id = request.GET.get("depart_id", "").strip()

    # select_related优化关联查询；显式排序，避免分页结果重复或漏项
    queryset = Employee.objects.all().select_related("depart").order_by("id")
    if keyword:
        queryset = queryset.filter(name__contains=keyword)
    if depart_id.isdigit():
        queryset = queryset.filter(depart_id=int(depart_id))

    # 分页，每页8条
    paginator = Paginator(queryset, 8)
    page_obj = paginator.get_page(request.GET.get("page", 1))

    depart_list = Department.objects.all()
    return render(request, "app01/employee_list.html", {
        "page_obj": page_obj,
        "depart_list": depart_list,
        "keyword": keyword,
        "depart_id": int(depart_id) if depart_id.isdigit() else "",
    })


def employee_add(request):
    """新建员工"""
    if request.method == "GET":
        form = EmployeeModelForm()
        return render(request, "app01/employee_change.html", {"form": form})

    # 带文件上传要用request.FILES
    form = EmployeeModelForm(data=request.POST, files=request.FILES)
    if form.is_valid():
        form.save()
        return redirect("/employee/list/")
    return render(request, "app01/employee_change.html", {"form": form})


def employee_edit(request, pk):
    """编辑员工"""
    employee = Employee.objects.filter(id=pk).first()
    if not employee:
        return redirect("/employee/list/")

    if request.method == "GET":
        form = EmployeeModelForm(instance=employee)
        return render(request, "app01/employee_change.html", {"form": form})

    form = EmployeeModelForm(data=request.POST, files=request.FILES, instance=employee)
    if form.is_valid():
        form.save()
        return redirect("/employee/list/")
    return render(request, "app01/employee_change.html", {"form": form})


@require_POST
def employee_delete(request, pk):
    """删除员工"""
    Employee.objects.filter(id=pk).delete()
    return redirect("/employee/list/")
