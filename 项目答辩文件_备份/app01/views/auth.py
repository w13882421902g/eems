"""
认证相关视图：登录、注销、验证码
"""
from django.shortcuts import render, redirect
from django.http import HttpResponse
from app01.models import User
from app01.utils.captcha import captcha_image_stream


def image_code(request):
    """生成验证码图片"""
    image_bytes, code_str = captcha_image_stream()
    # 验证码存入session
    request.session["image_code"] = code_str
    return HttpResponse(image_bytes, content_type="image/png")


def login(request):
    """用户登录"""
    if request.method == "GET":
        return render(request, "app01/login.html")

    # POST：获取表单数据
    username = request.POST.get("username", "")
    password = request.POST.get("password", "")
    input_code = request.POST.get("img_code", "")

    # 验证码取出即失效，避免同一条验证码被反复重放
    session_code = request.session.pop("image_code", "")

    # 校验验证码（不区分大小写）
    if not input_code or input_code.upper() != session_code.upper():
        return render(request, "app01/login.html", {"error": "验证码错误"})

    # 查询用户
    user = User.objects.filter(username=username).first()
    if not user:
        return render(request, "app01/login.html", {"error": "用户名不存在"})

    # 停用账号不允许登录
    if not user.is_active:
        return render(request, "app01/login.html", {"error": "账号已停用，请联系管理员"})

    # 校验密码（Django安全哈希）
    if not user.check_password(password):
        return render(request, "app01/login.html", {"error": "密码错误"})

    # 登录成功：换一个session标识，避免会话固定攻击
    request.session.cycle_key()
    request.session["user_id"] = user.id
    request.session["user_name"] = user.username
    return redirect("/depart/list/")


def logout(request):
    """注销"""
    request.session.flush()
    return redirect("/login/")
