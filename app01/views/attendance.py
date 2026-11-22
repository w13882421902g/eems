"""
考勤管理视图

核心业务规则：考勤状态不手工填，由 calc_status 根据上下班时间自动判定。
规则：
- 没有上班打卡记录 -> 缺勤(4)
- 上班时间晚于 09:00 -> 迟到(2)
- 有下班时间且早于 18:00 -> 早退(3)
- 其余 -> 按时(1)
"""
import datetime
from django.shortcuts import render, redirect
from django.views.decorators.http import require_POST
from app01.models import Attendance
from app01.forms import AttendanceModelForm
from app01.utils.scope import (
    can_manage, deny, scope_attendance, scope_employees, scope_of, SELF,
)


def _limit_form(form, user):
    """考勤表单里的员工下拉框只给当前账号数据范围内的人（员工本人则只有自己）"""
    if "employee" in form.fields:
        form.fields["employee"].queryset = scope_employees(user)
    return form


def calc_status(check_in, check_out):
    """
    根据上下班时间自动计算考勤状态。

    参数用 datetime.time 类型；check_in / check_out 允许为 None。
    返回值对应 Attendance.STATUS_CHOICES 的枚举值。
    """
    # 没有上班记录视为缺勤
    if not check_in:
        return 4
    # 晚于 9:00 上班算迟到（严格大于，9:00 整点算按时）
    if check_in > datetime.time(9, 0):
        return 2
    # 有下班记录且早于 18:00 算早退（没有下班记录不算早退，按按时处理）
    if check_out and check_out < datetime.time(18, 0):
        return 3
    # 其他情况按时
    return 1


def attendance_list(request):
    """考勤列表：按数据范围过滤，select_related 一次性取出员工，避免模板循环查库"""
    user = getattr(request, "current_user", None)
    queryset = scope_attendance(user)
    return render(request, "app01/attendance_list.html", {
        "attendance_list": queryset,
        "can_manage": can_manage(user),
        "is_self_scope": scope_of(user) == SELF,
    })


def attendance_add(request):
    """新增考勤（普通员工只读；部门管理员只能录本部门员工）"""
    user = getattr(request, "current_user", None)
    if not can_manage(user):
        return deny(request, "普通员工只能查看本人考勤，不能新增")
    if request.method == "GET":
        form = _limit_form(AttendanceModelForm(), user)
        return render(request, "app01/attendance_change.html", {"form": form})

    form = _limit_form(AttendanceModelForm(data=request.POST), user)
    if form.is_valid():
        # commit=False：先构造对象但不写库，等状态算完再统一 save
        attendance = form.save(commit=False)
        attendance.status = calc_status(attendance.check_in, attendance.check_out)
        attendance.save()
        return redirect("/attendance/list/")
    return render(request, "app01/attendance_change.html", {"form": form})


def attendance_edit(request, pk):
    """编辑考勤：修改时间后必须重新计算状态，否则状态会和实际时间不一致"""
    user = getattr(request, "current_user", None)
    if not can_manage(user):
        return deny(request, "普通员工只能查看本人考勤，不能修改")
    attendance = scope_attendance(user).filter(id=pk).first()
    if not attendance:
        return deny(request, "该考勤记录不在你的数据范围内")

    if request.method == "GET":
        form = _limit_form(AttendanceModelForm(instance=attendance), user)
        return render(request, "app01/attendance_change.html", {"form": form})

    form = _limit_form(AttendanceModelForm(data=request.POST, instance=attendance), user)
    if form.is_valid():
        obj = form.save(commit=False)
        obj.status = calc_status(obj.check_in, obj.check_out)
        obj.save()
        return redirect("/attendance/list/")
    return render(request, "app01/attendance_change.html", {"form": form})


@require_POST
def attendance_delete(request, pk):
    """删除考勤（只接受 POST；且必须在自己的数据范围内）"""
    user = getattr(request, "current_user", None)
    if not can_manage(user):
        return deny(request, "普通员工没有删除考勤记录的权限")
    if not scope_attendance(user).filter(id=pk).exists():
        return deny(request, "该考勤记录不在你的数据范围内")
    Attendance.objects.filter(id=pk).delete()
    return redirect("/attendance/list/")
