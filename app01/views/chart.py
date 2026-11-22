"""
数据统计可视化视图

后端只负责“查数据、拼 JSON”，画图交给前端 ECharts：
- /chart/                  统计页面（三个图表容器）
- /chart/depart/people/    各部门人数（饼图数据）
- /chart/salary/trend/     各月实发工资（折线图数据）
- /chart/depart/salary/    各部门实发工资总额（柱状图数据）

ORM 用法说明：
values("depart__title") 是按关联字段分组，annotate(Count("id")) 是组内计数，
等价于 SQL：SELECT depart_id, COUNT(id) ... GROUP BY depart_id。
"""
from django.db.models import Count, Sum
from django.shortcuts import render
from django.http import JsonResponse
from app01.models import Employee, Salary
from app01.utils.scope import scope_employees, scope_label, scope_of, scope_salary


def _user(request):
    return getattr(request, "current_user", None)


def chart_index(request):
    """数据统计页面"""
    return render(request, "app01/chart.html", {
        "scope_label": scope_label(_user(request)),
        "is_self_scope": scope_of(_user(request)) == "self",
    })


def chart_depart_people(request):
    """AJAX 接口：各部门人数分布（返回 [{"name": 部门, "value": 人数}]）"""
    queryset = scope_employees(_user(request)).values("depart__title").annotate(
        count=Count("id")
    ).order_by()   # order_by() 清空默认排序，避免无意义的排序开销
    data = [
        {"name": row["depart__title"] or "未分配部门", "value": row["count"]}
        for row in queryset
    ]
    return JsonResponse({"status": True, "data": data})


def chart_salary_trend(request):
    """AJAX 接口：各月实发工资趋势（返回月份数组和金额数组）"""
    queryset = scope_salary(_user(request)).values("month").annotate(
        total=Sum("total")
    ).order_by("month")   # 按月份升序，折线图时间轴才正确

    months = [row["month"] for row in queryset]
    # Decimal 不能直接 JSON 序列化，这里转成 float 给前端画图
    totals = [float(row["total"]) for row in queryset]
    return JsonResponse({"status": True, "months": months, "totals": totals})


def chart_depart_salary(request):
    """
    AJAX 接口：各部门实发工资总额（柱状图数据）

    返回结构与讲义第 19 章保持一致：
    {"status": True, "data": {"legend": [...], "x_axis": [...], "series_list": [...]}}

    这相当于 SQL：
        SELECT depart.title, SUM(salary.total)
        FROM salary JOIN employee JOIN department
        GROUP BY depart.title
    """
    queryset = scope_salary(_user(request)).values("employee__depart__title").annotate(
        total=Sum("total")
    ).order_by("-total")   # 金额高的部门排在前面，柱状图更有可读性

    x_axis = [row["employee__depart__title"] or "未分配部门" for row in queryset]
    # 空数据时给一组空坐标轴，前端仍然能正常 setOption，不会报错
    series_list = [{
        "name": "实发工资总额",
        "type": "bar",
        "barMaxWidth": 60,
        "data": [float(row["total"] or 0) for row in queryset],
    }]
    return JsonResponse({
        "status": True,
        "data": {"legend": ["实发工资总额"], "x_axis": x_axis, "series_list": series_list}
    })
