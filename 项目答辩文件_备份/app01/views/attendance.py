"""
考勤管理视图
"""
import datetime
from django.shortcuts import render, redirect
from django.views.decorators.http import require_POST
from app01.models import Attendance
from app01.forms import AttendanceModelForm


def calc_status(check_in, check_out):
    """根据上下班时间自动计算考勤状态"""
    # 没有上班记录视为缺勤
    if not check_in:
        return 4
    # 晚于9:00上班算迟到
    if check_in > datetime.time(9, 0):
        return 2
    # 有下班记录且早于18:00算早退
    if check_out and check_out < datetime.time(18, 0):
        return 3
    # 其他情况按时
    return 1


def attendance_list(request):
    """考勤列表"""
    queryset = Attendance.objects.all().select_related("employee")
    return render(request, "app01/attendance_list.html", {"attendance_list": queryset})


def attendance_add(request):
    """新增考勤"""
    if request.method == "GET":
        form = AttendanceModelForm()
        return render(request, "app01/attendance_change.html", {"form": form})

    form = AttendanceModelForm(data=request.POST)
    if form.is_valid():
        # commit=False先不写入数据库，计算状态后再保存
        attendance = form.save(commit=False)
        attendance.status = calc_status(attendance.check_in, attendance.check_out)
        attendance.save()
        return redirect("/attendance/list/")
    return render(request, "app01/attendance_change.html", {"form": form})


def attendance_edit(request, pk):
    """编辑考勤"""
    attendance = Attendance.objects.filter(id=pk).first()
    if not attendance:
        return redirect("/attendance/list/")

    if request.method == "GET":
        form = AttendanceModelForm(instance=attendance)
        return render(request, "app01/attendance_change.html", {"form": form})

    form = AttendanceModelForm(data=request.POST, instance=attendance)
    if form.is_valid():
        obj = form.save(commit=False)
        obj.status = calc_status(obj.check_in, obj.check_out)
        obj.save()
        return redirect("/attendance/list/")
    return render(request, "app01/attendance_change.html", {"form": form})


@require_POST
def attendance_delete(request, pk):
    """删除考勤"""
    Attendance.objects.filter(id=pk).delete()
    return redirect("/attendance/list/")
