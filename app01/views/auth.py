"""
认证相关视图：登录、注销、验证码

登录流程（答辩可重点讲）：
1. 浏览器打开登录页，页面里的 <img src="/image/code/"> 请求验证码图片；
2. 服务端生成 5 位随机字符，同时把明文验证码写入 session；
3. 用户提交账号、密码、验证码，服务端先校验验证码（取出即失效，防重放），
   再判断用户是否存在、是否启用，最后用 check_password 校验密码哈希；
4. 校验通过后 cycle_key() 更换 session 标识，写入 user_id / user_name，
   跳转到部门列表页。
"""
from django.shortcuts import render, redirect
from django.http import HttpResponse
from app01.models import User
from app01.utils.captcha import captcha_image_stream


def image_code(request):
    """
    生成验证码图片。

    返回的是 PNG 字节流，浏览器直接当图片显示；
    同时把验证码字符串存进 session，供登录时比对。
    """
    image_bytes, code_str = captcha_image_stream()
    # 验证码明文只保存在服务端 session，不随图片返回，避免被前端直接读取
    request.session["image_code"] = code_str
    return HttpResponse(image_bytes, content_type="image/png")


def login(request):
    """用户登录（GET 渲染页面，POST 校验并建立会话）"""
    if request.method == "GET":
        return render(request, "app01/login.html")

    # POST：获取表单数据（用 get 并给默认值，缺少字段时不会抛异常）
    username = request.POST.get("username", "")
    password = request.POST.get("password", "")
    input_code = request.POST.get("img_code", "")

    # 验证码取出即失效：pop 会删除 session 中的值，
    # 因此同一个验证码不能用第二次（防重放，见 tests.py 的 test_captcha_is_single_use）
    session_code = request.session.pop("image_code", "")

    # 校验验证码（统一转大写比较，忽略大小写差异）
    if not input_code or input_code.upper() != session_code.upper():
        return render(request, "app01/login.html", {"error": "验证码错误"})

    # 查询用户：用户名不存在时给出明确提示
    user = User.objects.filter(username=username).first()
    if not user:
        return render(request, "app01/login.html", {"error": "用户名不存在"})

    # 停用账号不允许登录（管理员可以在用户管理里停用账号）
    if not user.is_active:
        return render(request, "app01/login.html", {"error": "账号已停用，请联系管理员"})

    # 校验密码：check_password 会用同样的盐和算法重新哈希后比对，不接触明文
    if not user.check_password(password):
        return render(request, "app01/login.html", {"error": "密码错误"})

    # 登录成功：换一个 session 标识，避免会话固定攻击（Session Fixation）
    request.session.cycle_key()
    request.session["user_id"] = user.id
    request.session["user_name"] = user.username
    # 登录后进入首页：首页会按角色展示不同数据范围，比固定跳某个业务页更直观
    return redirect("/home/")


def logout(request):
    """注销登录：清空整个 session（包括登录态和验证码）"""
    request.session.flush()
    return redirect("/login/")
