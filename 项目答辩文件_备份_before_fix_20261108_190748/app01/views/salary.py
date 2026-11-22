"""
薪资管理视图
"""
from django.db.models import Sum
from django.shortcuts import render, redirect
from app01.models import Salary
from app01.forms import SalaryModelForm


def salary_list(request):
    """薪资列表（月份/员工筛选、总额统计）"""
    month = request.GET.get("month", "")
    employee_id = request.GET.get("employee_id", "")

    queryset = Salary.objects.all().select_related("employee")
    if month:
        queryset = queryset.filter(month=month)
    if employee_id:
        queryset = queryset.filter(employee_id=employee_id)

    # 统计当前筛选结果的实发总额
    total_sum = queryset.aggregate(sum_total=Sum("total"))["sum_total"] or 0

    return render(request, "app01/salary_list.html", {
        "salary_list": queryset,
        "month": month,
        "total_sum": total_sum,
    })


def salary_add(request):
    """新增薪资"""
    if request.method == "GET":
        form = SalaryModelForm()
        return render(request, "app01/salary_change.html", {"form": form})

    form = SalaryModelForm(data=request.POST)
    if form.is_valid():
        # commit=False计算实发后再保存
        salary = form.save(commit=False)
        salary.total = salary.base_salary + salary.bonus - salary.deduction
        salary.save()
        return redirect("/salary/list/")
    return render(request, "app01/salary_change.html", {"form": form})


def salary_edit(request, pk):
    """编辑薪资"""
    salary = Salary.objects.filter(id=pk).first()
    if not salary:
        return redirect("/salary/list/")

    if request.method == "GET":
        form = SalaryModelForm(instance=salary)
        return render(request, "app01/salary_change.html", {"form": form})

    form = SalaryModelForm(data=request.POST, instance=salary)
    if form.is_valid():
        obj = form.save(commit=False)
        obj.total = obj.base_salary + obj.bonus - obj.deduction
        obj.save()
        return redirect("/salary/list/")
    return render(request, "app01/salary_change.html", {"form": form})


def salary_delete(request, pk):
    """删除薪资"""
    Salary.objects.filter(id=pk).delete()
    return redirect("/salary/list/")
