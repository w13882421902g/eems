"""
登录认证中间件
"""
from django.utils.deprecation import MiddlewareMixin
from django.shortcuts import redirect


class AuthMiddleware(MiddlewareMixin):
    """统一登录校验，未登录访问受保护页面自动跳转登录页"""

    # 不需要登录就能访问的路径（精确匹配）
    WHITE_LIST = ["/login/", "/image/code/"]

    # 不需要登录就能访问的前缀：静态资源、媒体文件
    # 否则未登录时 CSS/图片 会被重定向成登录页，导致登录页失去样式
    WHITE_PREFIX = ("/static/", "/media/")

    def process_request(self, request):
        path = request.path_info

        # 白名单路径直接放行
        if path in self.WHITE_LIST or path.startswith(self.WHITE_PREFIX):
            return None

        # 从session读取用户信息，能读到说明已登录
        user_id = request.session.get("user_id")
        if user_id:
            return None

        # 未登录，跳转登录页
        return redirect("/login/")
