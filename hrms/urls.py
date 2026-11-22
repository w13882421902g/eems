"""
URL 路由配置（前端请求与后端视图的对应关系）

组织方式：
- 每个业务模块一组 CRUD 路由：list / add / edit / delete；
- 删除类接口只接受 POST（视图里用 @require_POST 强约束）；
- 任务模块用 AJAX 接口 task/add/ajax/；
- 统计模块拆成“页面 + 三个 JSON 数据接口”；
- 对照参考仓库补充：首页 /home/、AI 流式对话与浮窗辅助接口。
"""
from django.urls import path
from django.conf import settings
from django.conf.urls.static import static
from app01 import views

urlpatterns = [
    # ===== 认证与首页 =====
    path("", views.login),                 # 访问根路径直接进登录页
    path("login/", views.login),
    path("logout/", views.logout),
    path("image/code/", views.image_code), # 验证码图片
    path("home/", views.home),             # 按角色展示数据范围的首页

    # ===== 部门管理 =====
    path("depart/list/", views.department_list),
    path("depart/add/", views.department_add),
    path("depart/edit/<int:pk>/", views.department_edit),   # <int:pk> 只匹配数字，非法 id 直接 404
    path("depart/delete/<int:pk>/", views.department_delete),
    path("depart/multi/", views.department_multi),          # Excel 批量导入（只接受 POST）

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
    path("notice/top/<int:pk>/", views.notice_top),         # 置顶切换
    path("notice/delete/<int:pk>/", views.notice_delete),

    # ===== 任务管理（AJAX） =====
    path("task/list/", views.task_list),
    path("task/add/ajax/", views.task_add_ajax),            # 返回 JSON
    path("task/delete/<int:pk>/", views.task_delete),

    # ===== 订单管理（AJAX 弹窗） =====
    path("order/list/", views.order_list),
    path("order/add/", views.order_add),                    # POST 返回 JSON
    path("order/delete/", views.order_delete),              # POST，参数 uid
    path("order/detail/", views.order_detail),              # GET，参数 uid
    path("order/edit/", views.order_edit),                  # POST，参数 uid

    # ===== 数据统计 =====
    path("chart/", views.chart_index),
    path("chart/depart/people/", views.chart_depart_people),  # 饼图数据
    path("chart/salary/trend/", views.chart_salary_trend),    # 折线图数据
    path("chart/depart/salary/", views.chart_depart_salary),  # 柱状图数据

    # ===== 用户管理（仅超级管理员） =====
    path("user_manage/list/", views.user_list),
    path("user_manage/add/", views.user_add),
    path("user_manage/edit/<int:pk>/", views.user_edit),
    path("user_manage/reset/<int:pk>/", views.user_reset_pwd),
    path("user_manage/delete/<int:pk>/", views.user_delete),

    # ===== 角色管理（仅超级管理员） =====
    path("role/list/", views.role_list),
    path("role/add/", views.role_add),
    path("role/edit/<int:pk>/", views.role_edit),
    path("role/delete/<int:pk>/", views.role_delete),

    # ===== AI 智能助手 =====
    path("ai/", views.ai_assistant),                       # AI 助手工作台
    path("ai/assistant/", views.ai_assistant),             # 参考仓库地址，做别名
    path("ai/jd/", views.generate_jd),                     # T2 招聘 JD 生成
    path("ai/knowledge/qa/", views.knowledge_qa),          # T3 制度知识库问答
    path("ai/kb/", views.ai_kb),                           # T3 别名
    path("ai/comment/", views.salary_comment),             # T4 数据智能点评
    path("ai/review/", views.ai_review),                   # T4 别名
    path("ai/chat/", views.chat_ajax),                     # T5 多轮对话（表单版）
    path("ai/chat/stream/", views.ai_chat_stream),         # T5 多轮对话（SSE 流式）
    path("ai/chat/commit/", views.ai_chat_commit),         # 流式回答写入历史
    path("ai/chat/clear/", views.ai_chat_clear),           # 清空历史
    path("ai/chat/history/", views.ai_chat_history),       # 读取历史（浮窗）
    path("ai/csrf/", views.ai_csrf),                       # 下发 csrftoken
]

# 开发环境媒体文件访问：DEBUG=True 时由 Django 直接提供 /media/ 下的头像文件；
# 生产环境应交给 Nginx 等静态服务器，避免 Django 处理大文件。
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
