"""
部门管理视图（标准 CRUD + Excel 批量导入）

路由（见 hrms/urls.py）：
    GET  /depart/list/          部门列表（分页）
    GET  /depart/add/           新建页面
    POST /depart/add/           提交新建
    GET  /depart/edit/<pk>/     编辑页面
    POST /depart/edit/<pk>/     提交编辑
    POST /depart/delete/<pk>/   删除（只允许 POST，防 CSRF/误删）
    POST /depart/multi/         批量导入（Excel 上传，对应讲义第 17 章）
"""
import os

from django.contrib import messages
from django.shortcuts import render, redirect
from django.views.decorators.http import require_POST
from app01.models import Department, User
from app01.utils.pagination import Pagination
from app01.utils.scope import (
    can_manage, deny, is_dept_admin, is_super_admin, my_department_ids,
    require_super, scope_departments, scope_users,
)

# 导入限制：Excel 只允许这两种后缀，大小限制 5MB，避免解析超大文件拖垮服务
ALLOWED_EXCEL_EXT = (".xlsx", ".xlsm")
MAX_EXCEL_SIZE = 5 * 1024 * 1024
MAX_TITLE_LENGTH = Department._meta.get_field("title").max_length


def department_list(request):
    """部门列表（分页，按当前账号的数据范围过滤）"""
    # select_related("leader")：一次 JOIN 把负责人用户记录一起查出来，
    # 避免模板里循环访问 depart.leader 时每条记录再查一次数据库（N+1 问题）
    user = getattr(request, "current_user", None)
    queryset = scope_departments(user).order_by("id")
    page_object = Pagination(request, queryset, page_size=10)
    return render(request, "app01/department_list.html", {
        "page_queryset": page_object.page_queryset,
        "page_string": page_object.html(),
        "total_count": page_object.total_count,
        # 模板据此决定是否显示“新建 / 编辑 / 删除”按钮
        "can_manage": can_manage(user),
        "is_super_scope": is_super_admin(user),
    })


def department_add(request):
    """新建部门（仅超级管理员；部门结构变更属于系统级操作）"""
    user = getattr(request, "current_user", None)
    blocked = require_super(request)
    if blocked:
        return blocked

    if request.method == "GET":
        # 用户列表用于页面下拉框选择部门负责人（负责部门的人才算部门管理员）
        user_list = scope_users(user)
        return render(request, "app01/department_change.html", {"user_list": user_list})

    # POST：获取表单数据并校验后创建
    title = request.POST.get("title", "").strip()
    leader_id = request.POST.get("leader_id")

    # 名称非空 + 不重名：重名校验放在“创建之前”，
    # 不依赖数据库唯一约束，是因为历史上已有数据不一定带约束
    error = None
    if not title:
        error = "部门名称不能为空"
    elif len(title) > MAX_TITLE_LENGTH:
        error = f"部门名称不能超过 {MAX_TITLE_LENGTH} 个字符"
    elif Department.objects.filter(title=title).exists():
        error = "该部门已存在，请勿重复创建"

    if error:
        return render(request, "app01/department_change.html", {
            "user_list": scope_users(user),
            "form_title": title,
            "form_leader_id": leader_id,
            "error": error,
        })

    Department.objects.create(
        title=title,
        # 负责人可能为空（下拉框选择“------”），这里先判断是否为纯数字再转 int，
        # 避免空字符串转 int 抛 ValueError 导致 500
        leader_id=int(leader_id) if leader_id and leader_id.isdigit() else None
    )
    return redirect("/depart/list/")


def department_edit(request, pk):
    """编辑部门：超级管理员可编辑全部，部门管理员只能编辑自己负责的部门"""
    user = getattr(request, "current_user", None)
    if not can_manage(user):
        return deny(request, "普通员工没有编辑部门的权限")
    if not is_super_admin(user) and not is_dept_admin(user):
        return deny(request)

    # 先查记录：不存在时直接回列表页，避免对 None 继续操作
    depart = Department.objects.filter(id=pk).first()
    if not depart:
        return redirect("/depart/list/")
    # 部门管理员只能操作自己的部门，防止手改 URL 编辑其他部门
    if not is_super_admin(user) and depart.id not in my_department_ids(user):
        return deny(request, "你只能编辑自己负责的部门")

    if request.method == "GET":
        user_list = scope_users(user)
        return render(request, "app01/department_change.html", {
            "depart": depart, "user_list": user_list
        })

    # POST：更新数据（同样做非空与重名校验，排除自己）
    title = request.POST.get("title", "").strip()
    leader_id = request.POST.get("leader_id")

    error = None
    if not title:
        error = "部门名称不能为空"
    elif len(title) > MAX_TITLE_LENGTH:
        error = f"部门名称不能超过 {MAX_TITLE_LENGTH} 个字符"
    elif Department.objects.filter(title=title).exclude(id=depart.id).exists():
        error = "该部门名称已被占用"

    if error:
        return render(request, "app01/department_change.html", {
            "depart": depart,
            "user_list": scope_users(user),
            "form_title": title,
            "form_leader_id": leader_id,
            "error": error,
        })

    depart.title = title
    depart.leader_id = int(leader_id) if leader_id and leader_id.isdigit() else None
    depart.save()
    return redirect("/depart/list/")


@require_POST
def department_delete(request, pk):
    """
    删除部门（仅超级管理员）。

    @require_POST 的作用：
    1. 浏览器地址栏直接访问该 URL（GET）会返回 405，避免“打开链接就删数据”；
    2. 配合模板里的 csrf_token，防止第三方页面伪造 POST 请求。

    额外保护：部门下还有员工时禁止删除，避免员工档案的 depart 变成脏数据。
    """
    blocked = require_super(request)
    if blocked:
        return blocked
    depart = Department.objects.filter(id=pk).first()
    if depart and depart.employee_set.exists():
        return deny(request, "该部门下还有员工，请先转移员工后再删除部门")
    Department.objects.filter(id=pk).delete()
    return redirect("/depart/list/")


@require_POST
def department_multi(request):
    """
    批量导入部门（Excel 文件上传，对应讲义第 17 章）。

    文件上传三要素缺一不可：method="post"、enctype="multipart/form-data"、
    控件带 name（本页用 name="exc"）。文件不在 request.POST 里，而在 request.FILES 中。

    处理流程：
    1. 取 UploadedFile，校验存在性、后缀、大小；
    2. 交给 openpyxl 解析（它支持类文件对象，不需要先落盘）；
    3. 从第 2 行开始读第一列（第 1 行当表头），逐行去重后入库；
    4. 把“新增 / 重复跳过 / 空行跳过”的数量用 messages 回显到列表页。
    """
    upload = request.FILES.get("exc")
    # 批量导入属于系统级数据操作，仅超级管理员可用
    blocked = require_super(request)
    if blocked:
        return blocked

    # 1) 基础校验：没选文件、后缀不对、文件过大都直接给出提示
    if not upload:
        messages.error(request, "请选择要上传的 Excel 文件")
        return redirect("/depart/list/")
    if not upload.name.lower().endswith(ALLOWED_EXCEL_EXT):
        messages.error(request, "仅支持 .xlsx / .xlsm 格式的 Excel 文件")
        return redirect("/depart/list/")
    if upload.size > MAX_EXCEL_SIZE:
        messages.error(request, "文件不能超过 5MB")
        return redirect("/depart/list/")

    try:
        from openpyxl import load_workbook
    except ImportError:
        messages.error(request, "服务器未安装 openpyxl，请先执行 pip install openpyxl")
        return redirect("/depart/list/")

    # 2) 解析：read_only 降低内存占用，data_only 拿到公式计算结果而不是公式本身
    try:
        workbook = load_workbook(upload, read_only=True, data_only=True)
    except Exception:
        # 文件损坏、加密、不是真正的 xlsx 都会走到这里，不能把异常抛给用户看
        messages.error(request, "文件解析失败，请确认上传的是有效的 Excel 文件")
        return redirect("/depart/list/")

    sheet = workbook.worksheets[0]
    created = 0          # 新增条数
    skipped_duplicate = 0  # 已存在、跳过
    skipped_empty = 0      # 空行、跳过
    skipped_long = 0       # 名称超长、跳过

    try:
        # min_row=2：跳过表头；max_col=1：只看第一列，避免读到其他无关列
        for row in sheet.iter_rows(min_row=2, max_col=1, values_only=True):
            value = row[0] if row else None
            # Excel 里纯数字会被读成 float（如 1001.0），先还原成整数字符串
            if isinstance(value, float) and value.is_integer():
                value = int(value)
            title = str(value).strip() if value is not None else ""

            if not title:
                skipped_empty += 1
                continue
            if len(title) > MAX_TITLE_LENGTH:
                skipped_long += 1
                continue
            # 数据库已存在同名部门（包括本次循环里刚创建的）就跳过，保证不重复入库
            if Department.objects.filter(title=title).exists():
                skipped_duplicate += 1
                continue

            Department.objects.create(title=title)
            created += 1
    finally:
        # 无论成功与否都要关闭工作簿，释放文件句柄
        workbook.close()

    # 3) 结果回显：成功用 success，其余用 warning，方便区分“导入成功但有跳过”
    if created:
        messages.success(request, f"批量导入完成：新增 {created} 个部门")
    if skipped_duplicate or skipped_empty or skipped_long:
        messages.warning(
            request,
            "已跳过：重复 %d 条、空行 %d 条、超长 %d 条" % (
                skipped_duplicate, skipped_empty, skipped_long
            )
        )
    if not created and not (skipped_duplicate or skipped_empty or skipped_long):
        messages.warning(request, "文件中没有可导入的部门数据")

    return redirect("/depart/list/")
