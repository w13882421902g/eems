"""
Django settings for hrms project.（企业员工管理系统 全局配置）

本文件集中管理：密钥、调试开关、应用注册、中间件、模板、数据库、
认证模型、密码策略、国际化、静态/媒体文件路径。

答辩说明：数据库口令、中间件顺序、AUTH_USER_MODEL 是三个常考点。
"""

import os
from pathlib import Path

# 项目根目录：settings.py 在 hrms/ 下，parent.parent 即项目根
BASE_DIR = Path(__file__).resolve().parent.parent


def _load_env_file(path):
    """
    读取项目根目录的 .env（不引入额外依赖，自己解析 KEY=VALUE）。

    规则：
    - 忽略空行与 # 注释；
    - 支持 value 两端带引号；
    - 系统环境变量优先：已经设置过的变量不会被 .env 覆盖，
      这样 CI / 服务器上仍可用真实环境变量注入，本地则用 .env 方便演示。
    """
    if not path.exists():
        return
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except OSError:
        return
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        if key and key not in os.environ:
            os.environ[key] = value


_load_env_file(BASE_DIR / ".env")

# 安全密钥（开发环境使用；正式部署应改为环境变量读取，不要提交到代码仓库）
SECRET_KEY = 'django-insecure-(tx9nj9-%0j3-@tqyrg$rm3ytzm_$h9e3eke)x^es#sxv_yo!v'

# 调试模式：True 时会显示详细错误页、并提供 /media/ 静态文件访问
DEBUG = True

# 允许访问的域名/IP，"*" 表示开发阶段不限制
ALLOWED_HOSTS = ["*"]

# 应用注册
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'app01',                 # 业务应用：模型、视图、表单、模板都在这里
]

# 中间件
# 顺序很重要：请求自上而下进入、响应自下而上返回。
# AuthMiddleware 放在最后，保证 session 中间件已经准备好、能读到 session。
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',          # CSRF 校验
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    # 自定义登录校验中间件（白名单放行 /login/、验证码、静态资源）
    'app01.middleware.auth.AuthMiddleware',
]

ROOT_URLCONF = 'hrms.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,        # 启用 app 内 templates 目录自动发现
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',   # 模板里可用 request
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                # 自定义上下文处理器：按角色下发导航菜单、数据范围、当前用户
                'app01.context_processors.nav_context',
            ],
        },
    },
]

WSGI_APPLICATION = 'hrms.wsgi.application'

# 数据库配置（MySQL）
# 说明：项目通过 hrms/__init__.py 里的 pymysql.install_as_MySQLdb() 使用 PyMySQL 驱动。
# 连接参数与 MySQL 实际环境保持一致；口令属于本机开发配置。
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': 'hrms',          # 数据库名（需提前在 MySQL 中创建）
        'HOST': '127.0.0.1',
        'PORT': 3306,
        'USER': 'root',
        'PASSWORD': '123qwe',
    }
}

# 自定义用户模型：认证体系整体切换到 app01.User（含 roles 多对多）
AUTH_USER_MODEL = 'app01.User'

# 密码校验（Django 内置四项：与用户信息相似度、最小长度、常见弱密码、纯数字）
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# 国际化
LANGUAGE_CODE = 'zh-hans'      # 简体中文
TIME_ZONE = 'Asia/Shanghai'    # 东八区
USE_I18N = True
USE_TZ = False                 # 关闭 UTC 存储，时间字段按本地时间直接读写

# 静态文件（CSS、JS、Bootstrap 等）
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'static_collect'   # collectstatic 的输出目录

# 媒体文件（员工头像等上传内容）
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# 默认主键字段类型：BigAutoField（64 位自增，避免数据量大时主键溢出）
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# 登录页地址（中间件/装饰器未登录跳转时可复用）
LOGIN_URL = '/login/'

# ===== 大模型（LLM）配置 =====
# Key 读取顺序：系统环境变量 > 项目根目录 .env > 空值（走规则兜底）。
# 推荐做法：把 Key 写进项目根目录的 .env（已被 .gitignore 忽略，不会提交）：
#   AI_API_KEY=sk-xxxx
#   AI_BASE_URL=https://api.siliconflow.cn/v1
#   AI_MODEL=Qwen/Qwen2.5-7B-Instruct
# 可用 python manage.py check_ai 查看当前配置（Key 会脱敏显示）。
AI_API_KEY = os.environ.get("AI_API_KEY", "")
AI_BASE_URL = os.environ.get("AI_BASE_URL", "https://api.siliconflow.cn/v1")
AI_MODEL = os.environ.get("AI_MODEL", "Qwen/Qwen2.5-7B-Instruct")
# 单次调用超时（秒）：超时即走兜底提示，避免页面长时间转圈或崩溃
AI_TIMEOUT = int(os.environ.get("AI_TIMEOUT", "20"))
