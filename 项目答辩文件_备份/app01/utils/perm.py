"""
权限校验工具
"""
from functools import wraps

from django.http import HttpResponseForbidden

from app01.models import User


def superuser_required(view_func):
    """仅允许超级管理员访问；其他登录用户返回 403。

    当前项目登录态存在 session 的 user_id 上，未接入 request.user，
    因此这里按 session 中的 user_id 反查用户后判断。
    """

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        user = User.objects.filter(id=request.session.get("user_id")).only("is_superuser", "is_active").first()
        if not user or not user.is_active or not user.is_superuser:
            return HttpResponseForbidden("无权限访问：该功能仅限超级管理员")
        return view_func(request, *args, **kwargs)

    return wrapper
