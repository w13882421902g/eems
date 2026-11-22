"""
权限校验工具（函数装饰器）

使用场景：
    用户管理、角色管理等“系统级功能”只允许超级管理员操作，
    在视图函数上加 @superuser_required 即可，不需要在每个函数里重复判断。

设计说明：
    项目登录态存放在 session 的 user_id 上（没有使用 request.user），
    所以装饰器按 user_id 反查数据库用户，再判断 is_active 和超级管理员身份。
    对照参考仓库补充：超级管理员不再只看 is_superuser 标记，
    拥有“超级管理员”角色的账号同样算超管，避免角色管理和 is_superuser 两套口径打架。
"""
from functools import wraps

from app01.models import User
from app01.utils.scope import deny, is_super_admin


def superuser_required(view_func):
    """仅允许超级管理员访问；其他登录用户返回 403。

    执行流程：
    1. 优先用中间件挂到 request 上的 current_user，没有再按 session 反查；
    2. 用户不存在、被停用、不是超级管理员，一律返回 403；
    3. 校验通过才执行原视图函数。

    说明：@wraps 保留原函数的 __name__ 和 __doc__，方便调试和日志定位。
    """

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        user = getattr(request, "current_user", None)
        if not user:
            user = User.objects.prefetch_related("roles").filter(
                id=request.session.get("user_id")
            ).first()
        if not user or not user.is_active or not is_super_admin(user):
            return deny(request, "该功能仅限超级管理员")
        return view_func(request, *args, **kwargs)

    return wrapper
