"""
订单管理视图（Ajax + JSON 接口，对应讲义第 18 章）

和普通 CRUD 的区别：
- 页面不跳转，全部靠 jQuery Ajax 读写，后端只返回 JSON；
- 新建/编辑共用一个弹窗，前端用 EDIT_ID 区分“新增”还是“修改”；
- 订单号、管理员由后端生成：前端提交的表单里根本不包含这两个字段。

安全说明（与讲义示例的差异）：
讲义用 @csrf_exempt 图省事，本项目保留 Django 的 CSRF 校验，
由前端把令牌放进 X-CSRFToken 请求头，避免第三方页面伪造下单/删除请求。
"""
import random
from datetime import datetime

from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST

from app01 import models
from app01.forms import OrderModelForm
from app01.utils.pagination import Pagination


def _parse_uid(request, source="GET"):
    """
    统一解析订单 ID。

    - 参数可能是 "abc"、空串、负数，直接丢进 filter(id=xxx) 会抛 ValueError，
      所以先判断是否为数字；
    - 返回 (uid, 错误 JSON)，调用方拿到 uid 为 None 时直接返回错误。
    """
    raw = request.POST.get("uid") if source == "POST" else request.GET.get("uid")
    raw = (raw or "").strip() if isinstance(raw, str) else raw
    if not str(raw).isdigit():
        return None, JsonResponse({"status": False, "error": "参数错误，订单不存在。"})
    return int(raw), None


def _make_oid():
    """
    生成订单号：时间戳（14 位）+ 4 位随机数，例如 202611201530121234。

    和唯一约束配合使用：极端情况下随机数撞车，循环重新生成，
    保证不会因为“订单号重复”而导致插入失败。
    """
    while True:
        oid = datetime.now().strftime("%Y%m%d%H%M%S") + str(random.randint(1000, 9999))
        if not models.Order.objects.filter(oid=oid).exists():
            return oid


def order_list(request):
    """订单列表页：表格 + 新建/编辑弹窗 + 删除确认框，数据分页显示"""
    queryset = models.Order.objects.all().select_related("admin").order_by("-id")
    page_object = Pagination(request, queryset, page_size=10)
    form = OrderModelForm()

    return render(request, "app01/order_list.html", {
        "form": form,
        "queryset": page_object.page_queryset,
        "page_string": page_object.html(),
        "total_count": page_object.total_count,
    })


@require_POST
def order_add(request):
    """新建订单（Ajax POST，返回 JSON）"""
    form = OrderModelForm(data=request.POST)
    if not form.is_valid():
        # form.errors 的值是 ErrorList，这里取第一条转成字符串，前端直接显示
        return JsonResponse({
            "status": False,
            "error": {field: errors[0] for field, errors in form.errors.items()}
        })

    order = form.save(commit=False)          # 先不写库，补上后端字段后再保存
    order.oid = _make_oid()                  # 订单号由后端生成
    admin_id = request.session.get("user_id")
    if not admin_id:
        return JsonResponse({"status": False, "tips": "登录状态已失效，请重新登录。"})
    order.admin_id = admin_id                # 管理员取当前登录用户
    order.save()
    return JsonResponse({"status": True, "msg": "添加成功"})


@require_POST
def order_delete(request):
    """删除订单（Ajax POST）：数据不存在时返回明确提示，而不是静默成功"""
    uid, error_response = _parse_uid(request, source="POST")
    if error_response:
        return error_response

    deleted, _ = models.Order.objects.filter(id=uid).delete()
    if not deleted:
        return JsonResponse({"status": False, "error": "删除失败，数据不存在。"})
    return JsonResponse({"status": True})


def order_detail(request):
    """按 ID 返回订单详情，编辑弹窗打开前调用，用来回填表单"""
    uid, error_response = _parse_uid(request, source="GET")
    if error_response:
        return error_response

    row = models.Order.objects.filter(id=uid).values("title", "price", "status").first()
    if not row:
        return JsonResponse({"status": False, "error": "数据不存在。"})
    return JsonResponse({"status": True, "data": row})


@require_POST
def order_edit(request):
    """编辑订单（Ajax POST）：只允许改名称/价格/状态，订单号和管理员不在表单里"""
    uid, error_response = _parse_uid(request, source="GET")
    if error_response:
        return error_response

    row_object = models.Order.objects.filter(id=uid).first()
    if not row_object:
        return JsonResponse({"status": False, "tips": "数据不存在，请刷新重试。"})

    # instance=row_object：表单以原记录为底稿，只覆盖提交上来的字段
    form = OrderModelForm(data=request.POST, instance=row_object)
    if not form.is_valid():
        return JsonResponse({
            "status": False,
            "error": {field: errors[0] for field, errors in form.errors.items()}
        })

    form.save()
    return JsonResponse({"status": True, "msg": "修改成功"})
