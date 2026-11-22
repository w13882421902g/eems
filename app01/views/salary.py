"""
薪资管理视图

要点：
- 列表支持按月份筛选，并对“当前筛选结果”做总额统计；
- 实发工资在视图里算一次、在模型的 save() 里再统一算一次，
  最终以模型层为准，保证任何入口保存的数据口径一致。
"""
from django.db.models import Sum
from django.shortcuts import render, redirect
from django.views.decorators.http import require_POST
from app01.models import Salary
from app01.forms import SalaryModelForm
from app01.utils.scope import (
    can_manage, deny, scope_employees, scope_salary, scope_of, SELF,
)


def _limit_form(form, user):
    """薪资表单的员工下拉框只给数据范围内的人，员工本人则只有自己"""
    if "employee" in form.fields:
        form.fields["employee"].queryset = scope_employees(user)
    return form


def salary_list(request):
    """
    薪资列表（月份/员工筛选、总额统计）

    aggregate(Sum("total")) 会翻译成 SQL 的 SUM 聚合，
    只返回一个总数，不把明细全部取到内存里再累加，数据量大时更省资源。
    没有任何记录时 Sum 返回 None，这里兜底为 0，避免模板显示 None。
    """
    month = request.GET.get("month", "")
    employee_id = request.GET.get("employee_id", "").strip()
    user = getattr(request, "current_user", None)

    # 先按数据范围过滤，再做月份/员工筛选
    queryset = scope_salary(user)
    if month:
        queryset = queryset.filter(month=month)
    if employee_id.isdigit():
        queryset = queryset.filter(employee_id=int(employee_id))

    # 统计当前筛选结果的实发总额
    total_sum = queryset.aggregate(sum_total=Sum("total"))["sum_total"] or 0

    return render(request, "app01/salary_list.html", {
        "salary_list": queryset,
        "month": month,
        "total_sum": total_sum,
        "can_manage": can_manage(user),
        "is_self_scope": scope_of(user) == SELF,
    })


def salary_add(request):
    """新增薪资（普通员工只读；部门管理员只能录本部门员工）"""
    user = getattr(request, "current_user", None)
    if not can_manage(user):
        return deny(request, "普通员工只能查看本人薪资，不能新增")
    if request.method == "GET":
        form = _limit_form(SalaryModelForm(), user)
        return render(request, "app01/salary_change.html", {"form": form})

    form = _limit_form(SalaryModelForm(data=request.POST), user)
    if form.is_valid():
        # commit=False：先拿到对象，算出实发工资后再入库
        salary = form.save(commit=False)
        salary.total = salary.base_salary + salary.bonus - salary.deduction
        salary.save()
        return redirect("/salary/list/")
    return render(request, "app01/salary_change.html", {"form": form})


def salary_edit(request, pk):
    """编辑薪资：修改基本工资/奖金/扣款后重新计算实发工资"""
    user = getattr(request, "current_user", None)
    if not can_manage(user):
        return deny(request, "普通员工只能查看本人薪资，不能修改")
    salary = scope_salary(user).filter(id=pk).first()
    if not salary:
        return deny(request, "该薪资记录不在你的数据范围内")

    if request.method == "GET":
        form = _limit_form(SalaryModelForm(instance=salary), user)
        return render(request, "app01/salary_change.html", {"form": form})

    form = _limit_form(SalaryModelForm(data=request.POST, instance=salary), user)
    if form.is_valid():
        obj = form.save(commit=False)
        obj.total = obj.base_salary + obj.bonus - obj.deduction
        obj.save()
        return redirect("/salary/list/")
    return render(request, "app01/salary_change.html", {"form": form})


@require_POST
def salary_delete(request, pk):
    """删除薪资记录（只接受 POST；且必须在自己的数据范围内）"""
    user = getattr(request, "current_user", None)
    if not can_manage(user):
        return deny(request, "普通员工没有删除薪资记录的权限")
    if not scope_salary(user).filter(id=pk).exists():
        return deny(request, "该薪资记录不在你的数据范围内")
    Salary.objects.filter(id=pk).delete()
    return redirect("/salary/list/")
