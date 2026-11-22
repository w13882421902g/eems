"""
登录认证中间件（全局拦截器）

作用：在任何视图执行之前统一判断“是否已登录”，
避免每个视图函数里重复写登录判断，也防止漏写导致越权访问。

登录态的实现方式：
- 登录成功时，views/auth.py 把 user_id / user_name 写入 session；
- 本中间件从 session 读取 user_id，读得到就放行，读不到就跳登录页；
- 对照参考仓库补充：登录有效时把用户对象挂到 request.current_user，
  供 context_processors（导航菜单）与权限工具（scope）直接复用，避免重复查库。

安全补充：
- 账号被删除 / 被停用后，旧 session 仍然存在，这里统一清空 session 并踢回登录页，
  否则“停用账号”这个功能会被绕过去。
"""
from django.shortcuts import redirect
from django.utils.deprecation import MiddlewareMixin

from app01.models import User


class AuthMiddleware(MiddlewareMixin):
    """统一登录校验，未登录访问受保护页面自动跳转登录页"""

    # 白名单：不需要登录即可访问的精确路径
    # /login/ 是登录页本身；/image/code/ 是验证码图片，登录页必须能加载
    WHITE_LIST = ["/login/", "/image/code/"]

    # 前缀白名单：静态资源、媒体文件
    # 关键点：如果这里漏了 /static/，未登录时 CSS、图片请求也会被重定向到登录页，
    # 结果就是“登录页自己没有样式”，这是很典型的中间件踩坑点。
    WHITE_PREFIX = ("/static/", "/media/")

    def process_request(self, request):
        """每个请求进入视图前执行；返回 None 表示放行，返回响应对象表示直接中断。"""
        path = request.path_info

        # 1) 白名单路径直接放行
        if path in self.WHITE_LIST or path.startswith(self.WHITE_PREFIX):
            return None

        # 2) 从 session 读取 user_id，有值且账号有效说明已登录
        user_id = request.session.get("user_id")
        if user_id:
            user = User.objects.filter(id=user_id).only("id", "username", "is_active").first()
            if user and user.is_active:
                # 挂到 request 上：后续视图、权限工具、模板上下文处理器都能直接用
                request.current_user = user
                return None
            # 账号被删除或停用：清空会话，回到登录页
            request.session.flush()
            return redirect("/login/")

        # 3) 未登录：统一跳转到登录页
        return redirect("/login/")
