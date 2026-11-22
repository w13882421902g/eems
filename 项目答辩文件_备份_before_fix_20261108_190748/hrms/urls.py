"""
URL路由配置
"""
from django.urls import path
from django.conf import settings
from django.conf.urls.static import static
from app01 import views

urlpatterns = [
    # ===== 认证 =====
    path("", views.login),
    path("login/", views.login),
    path("logout/", views.logout),
    path("image/code/", views.image_code),

    # ===== 部门管理 =====
    path("depart/list/", views.department_list),
    path("depart/add/", views.department_add),
    path("depart/edit/<int:pk>/", views.department_edit),
    path("depart/delete/<int:pk>/", views.department_delete),

    # ===== 员工管理 =====
    path("employee/list/", views.employee_list),
    path("employee/add/", views.employee_add),
    path("employee/edit/<int:pk>/", views.employee_edit),
    path("employee/delete/<int:pk>/", views.employee_delete),

    # ===== 考勤管理 =====
    path("attendance/list/", views.attendance_list),
    path("attendance/add/", views.attendance_add),
    path("attendance/edit/<int:pk>/", views.attendance_edit),
    path("attendance/delete/<int:pk>/", views.attendance_delete),

    # ===== 薪资管理 =====
    path("salary/list/", views.salary_list),
    path("salary/add/", views.salary_add),
    path("salary/edit/<int:pk>/", views.salary_edit),
    path("salary/delete/<int:pk>/", views.salary_delete),

    # ===== 公告管理 =====
    path("notice/list/", views.notice_list),
    path("notice/add/", views.notice_add),
    path("notice/edit/<int:pk>/", views.notice_edit),
    path("notice/top/<int:pk>/", views.notice_top),
    path("notice/delete/<int:pk>/", views.notice_delete),

    # ===== 任务管理（AJAX） =====
    path("task/list/", views.task_list),
    path("task/add/ajax/", views.task_add_ajax),
    path("task/delete/<int:pk>/", views.task_delete),

    # ===== 数据统计 =====
    path("chart/", views.chart_index),
    path("chart/depart/people/", views.chart_depart_people),
    path("chart/salary/trend/", views.chart_salary_trend),

    # ===== 用户管理 =====
    path("user_manage/list/", views.user_list),
    path("user_manage/add/", views.user_add),
    path("user_manage/edit/<int:pk>/", views.user_edit),
    path("user_manage/reset/<int:pk>/", views.user_reset_pwd),
    path("user_manage/delete/<int:pk>/", views.user_delete),

    # ===== 角色管理 =====
    path("role/list/", views.role_list),
    path("role/add/", views.role_add),
    path("role/edit/<int:pk>/", views.role_edit),
    path("role/delete/<int:pk>/", views.role_delete),
]

# 开发环境媒体文件访问
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
