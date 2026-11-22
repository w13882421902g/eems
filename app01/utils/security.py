"""
AI 模块的安全与健壮性处理（对应任务书 T6，对照参考仓库移植）

1. 输入长度限制 + 控制字符清理 + 常见提示词注入话术拦截；
2. 简单的调用频率限制，避免被连续点击刷接口；
3. 所有校验失败都返回友好提示，不抛异常。
"""
import re
import time

from django.utils.html import strip_tags

MAX_LENGTH = {
    "chat": 500,
    "question": 300,
    "job_title": 30,
    "extra": 300,
    "default": 500,
}

# 常见的“提示词注入”话术：命中后不执行，直接友好拒绝
INJECTION_PATTERNS = (
    r"忽略(以上|之前|前面|上述)的?(所有)?(指令|提示|要求)",
    r"ignore\s+(the\s+)?(above|previous)",
    r"(system|system\s+prompt|系统提示词|系统指令)",
    r"开发者模式|developer\s+mode",
    r"(你现在是|从现在开始你是|扮演).{0,12}(不受限制|无限制|没有限制)",
    r"(输出|打印|泄露).{0,10}(密钥|api\s*key|密码|prompt)",
)

# 每秒最多调用一次，防止连续点击刷接口
MIN_INTERVAL = 1.0


def clean_text(raw, kind="default"):
    """
    清洗并校验输入。
    返回 (清洗后的文本, 错误提示)；错误提示为空字符串表示校验通过。
    """
    max_length = MAX_LENGTH.get(kind, MAX_LENGTH["default"])
    text = (raw or "")
    if not isinstance(text, str):
        text = str(text)
    # 去掉 HTML 标签、控制字符，压缩空白
    text = strip_tags(text)
    text = "".join(ch for ch in text if ch == "\n" or ch >= " ")
    text = re.sub(r"[ \t]+", " ", text).strip()
    if not text:
        return "", "内容不能为空"
    if len(text) > max_length:
        return "", f"内容过长（最多 {max_length} 字），请精简后再提交"
    for pattern in INJECTION_PATTERNS:
        if re.search(pattern, text, flags=re.IGNORECASE):
            return "", "输入内容包含不支持的指令，请用正常的问题提问"
    return text, ""


def check_rate(request):
    """简单频率限制：返回 (是否允许, 提示信息)"""
    now = time.time()
    last = request.session.get("_ai_last_call", 0)
    if now - float(last) < MIN_INTERVAL:
        return False, "操作太快了，请稍等 1 秒再试"
    request.session["_ai_last_call"] = now
    return True, ""
