"""
AI 智能助手视图（大模型功能闭环 + 对照参考仓库增强）

接口一览（保留原有路由，新增的接口供全局 AI 浮窗使用）：
    GET  /ai/            智能助手工作台（4 个功能页签）
    GET  /ai/assistant/  同上（参考仓库使用的地址，做别名）
    POST /ai/jd/         T2 智能生成招聘 JD
    POST /ai/knowledge/qa/  T3 制度知识库问答（保留原地址）
    POST /ai/kb/         T3 同上（参考仓库地址）
    POST /ai/comment/    T4 数据智能点评（保留原地址）
    POST /ai/review/     T4 同上（参考仓库地址）
    POST /ai/chat/       T5 多轮对话（表单版，兼容原页面）
    POST /ai/chat/stream/  T5 多轮对话（SSE 流式，浮窗使用）
    POST /ai/chat/commit/  流式结束后把回答写入会话历史
    POST /ai/chat/clear/   清空多轮对话历史
    GET  /ai/chat/history/ 读取与工作台共用的会话历史
    GET  /ai/csrf/         确保下发 csrftoken（浮窗缺少 cookie 时调用）

统一约定：
- 所有大模型调用走 LLMClient，并传入 fallback（规则兜底），未配 Key 也能完整演示；
- 前端 jQuery AJAX POST，返回 JSON：成功 {"status": True, "data": 文本}，失败 {"status": False, "error": 提示}；
- 数据类问题先查数据库（严格套用分级权限），制度类问题走 SQL 关键词检索 + 提示词注入。
"""
import calendar
import datetime
import json
import re
import time

from django.http import JsonResponse, StreamingHttpResponse
from django.shortcuts import render
from django.views.decorators.csrf import ensure_csrf_cookie

from app01.models import Attendance, Employee, Knowledge, Salary, User
from app01.utils import offline_ai
from app01.utils.ai import LLMClient
from app01.utils.data_qa import answer_data_question
from app01.utils.knowledge import docs_to_text, extract_terms, search_knowledge
from app01.utils.prompts import (
    JD_SYSTEM, build_jd_prompt,
    QA_SYSTEM, build_qa_prompt,
    COMMENT_SYSTEM, build_comment_prompt,
    CHAT_SYSTEM, build_chat_prompt,
)
from app01.utils.scope import (
    SELF, deny, my_employee, scope_employees, scope_of,
)
from app01.utils.security import check_rate, clean_text

# 自我介绍类问题固定回答（不经过模型，避免模型额外补充“查不到制度”之类的废话）
IDENTITY_KEYS = (
    "你是谁", "你叫什么", "你的名字", "介绍一下你",
    "你能做什么", "你能干什么", "你会什么", "你有哪些功能",
)
IDENTITY_ANSWER = (
    "我是wg，这个系统的 AI 助手。能帮你查制度、看考勤薪资和员工信息，也能写招聘 JD；"
    "回答只基于系统数据和制度库，查不到或没权限会直接告诉你。"
)

# 多轮对话历史存放在 session 中，只保留最近 3 轮（6 条消息）
HISTORY_KEY = "ai_chat_history"
HISTORY_LIMIT = 6


# --------------------------------------------------------------------------- #
# 通用小工具
# --------------------------------------------------------------------------- #
def _current_user(request):
    """当前登录用户：优先用中间件挂到 request 上的对象，兜底查 session"""
    user = getattr(request, "current_user", None)
    if user:
        return user
    user_id = request.session.get("user_id")
    return User.objects.filter(id=user_id).first() if user_id else None


def _json_body(request):
    """
    安全解析 JSON 请求体。

    只有 Content-Type 为 application/json 时才读 request.body：
    表单提交（application/x-www-form-urlencoded）下 request.body 已被 Django 解析过，
    再访问会抛 RawPostDataException，先判断类型可以避开这个坑。
    """
    if "application/json" not in (request.content_type or ""):
        return {}
    try:
        return json.loads(request.body.decode("utf-8") or "{}")
    except (ValueError, UnicodeDecodeError):
        return {}


def _payload(request, *keys):
    """同时兼容 JSON 请求体与表单 POST（老页面用表单，浮窗用 JSON）"""
    body = _json_body(request)
    result = {}
    for key in keys:
        value = body.get(key)
        if value is None:
            value = request.POST.get(key)
        result[key] = value
    return result


def _error(message):
    """统一的失败返回：同时给 error 和 msg，兼容两套前端写法"""
    return JsonResponse({"status": False, "error": message, "msg": message})


def _mode_text(result):
    """把调用模式翻译成前端展示文案"""
    mode = getattr(result, "mode", "llm")
    if mode == "llm":
        return "大模型生成"
    if mode == "rule":
        return "规则判定"
    return ""


def _history(request):
    history = request.session.get(HISTORY_KEY, [])
    return history if isinstance(history, list) else []


def _save_history(request, history):
    request.session[HISTORY_KEY] = history[-HISTORY_LIMIT:]


def _append_history(request, question, answer):
    """把一轮问答追加进 session 历史"""
    history = _history(request)
    history.append({"role": "user", "content": question})
    history.append({"role": "assistant", "content": str(answer)[:2000]})
    _save_history(request, history)
    return history


def _ok(text, mode="llm", error="", sources=None, **extra):
    """统一的成功返回：data 兼容老页面，answer 兼容参考仓库页面"""
    data = {
        "status": True,
        "data": str(text),
        "answer": str(text),
        "mode": mode,
        "mode_text": _mode_text_text(mode),
        "error": error,
        "sources": sources or [],
    }
    data.update(extra)
    return JsonResponse(data)


def _mode_text_text(mode):
    return {"llm": "大模型生成", "offline": "规则兜底", "data": "系统数据查询", "rule": "规则判定"}.get(mode, "")


# --------------------------------------------------------------------------- #
# 工作台页面
# --------------------------------------------------------------------------- #
@ensure_csrf_cookie
def ai_assistant(request):
    """AI 助手页面入口：向下拉框提供（数据范围内的）员工列表与可选月份。"""
    user = _current_user(request)
    employee_list = scope_employees(user).order_by("id") if user else Employee.objects.none()
    employee_rows = [
        {"id": item.id, "name": item.name, "depart": item.depart.title if item.depart else ""}
        for item in employee_list
    ]
    # 去重后的薪资月份，供点评模块选择；始终补上当前月
    months = list(Salary.objects.values_list("month", flat=True).distinct().order_by("-month"))
    current_month = datetime.date.today().strftime("%Y-%m")
    if current_month not in months:
        months.insert(0, current_month)
    return render(request, "app01/ai_assistant.html", {
        "employee_list": employee_list,
        "employee_rows": employee_rows,
        "month_list": months[:12],
        "months": months[:12],
        "current_month": current_month,
        "llm_configured": LLMClient().configured,
        "model_name": LLMClient().model,
        "knowledge_count": Knowledge.objects.count(),
        "scope": scope_of(user) if user else SELF,
        "my_emp": my_employee(user) if user else None,
        "history_count": len(_history(request)),
    })


# --------------------------------------------------------------------------- #
# T2 招聘 JD
# --------------------------------------------------------------------------- #
def generate_jd(request):
    """T2：输入岗位名称，返回结构化招聘 JD（职责 / 要求 / 薪资）。"""
    if request.method != "POST":
        return _error("请求方式错误")
    allowed, message = check_rate(request)
    if not allowed:
        return _error(message)
    values = _payload(request, "title", "job_title", "department", "level", "extra")
    title, error = clean_text(values.get("title") or values.get("job_title"), "job_title")
    if error:
        return _error("岗位名称" + error if "为空" in error else error)
    department = (values.get("department") or "").strip()[:30]
    level = (values.get("level") or "").strip()[:20]
    extra, _ = clean_text(values.get("extra"), "extra")

    result = LLMClient.chat(
        build_jd_prompt(title),
        system=JD_SYSTEM,
        temperature=0.7,
        fallback=offline_ai.jd_reply(title, department, level, extra),
    )
    return _ok(result, mode=getattr(result, "mode", "offline"), error=getattr(result, "error", ""))


ai_jd = generate_jd


# --------------------------------------------------------------------------- #
# T3 制度知识库问答
# --------------------------------------------------------------------------- #
def knowledge_qa(request):
    """T3：制度知识库问答。SQL 关键词检索相关条目 → 拼入提示词 → 返回答案。"""
    if request.method != "POST":
        return _error("请求方式错误")
    allowed, message = check_rate(request)
    if not allowed:
        return _error(message)
    values = _payload(request, "question")
    question, error = clean_text(values.get("question"), "question")
    if error:
        return _error(error)

    # 1) 关键词分词后做 OR 模糊检索，再按命中权重打分取最相关的 3 条
    docs = search_knowledge(question, top_k=3)
    if not docs:
        # 没检索到资料：直接兜底回答“不知道”，不调用模型
        text = f"不知道：制度库中没有检索到与「{question}」相关的规定，建议向人力资源部确认。"
        return _ok(text, mode="rule", sources=[], terms=extract_terms(question))

    # 2) 命中资料拼成上下文，限定“只根据资料回答”，防止模型胡编
    answer = LLMClient.chat(
        build_qa_prompt(docs_to_text(docs), question),
        system=QA_SYSTEM,
        temperature=0.2,
        fallback=offline_ai.kb_reply(question, docs),
    )
    answer_text = str(answer).strip()
    unknown = answer_text.startswith("不知道")
    sources = [] if unknown else [
        {"title": doc["title"], "category": doc["category"]} for doc in docs
    ]
    return _ok(
        answer_text,
        mode=getattr(answer, "mode", "offline"),
        error=getattr(answer, "error", ""),
        sources=sources,
        terms=extract_terms(question),
    )


ai_kb = knowledge_qa


# --------------------------------------------------------------------------- #
# T4 数据智能点评
# --------------------------------------------------------------------------- #
def _build_employee_data(employee, month):
    """把某员工某月的考勤/薪资数据转成文本（这就是“上下文注入”的原料）"""
    year, mon = (int(part) for part in month.split("-"))
    start = datetime.date(year, mon, 1)
    end = datetime.date(year, mon, calendar.monthrange(year, mon)[1])
    records = list(
        Attendance.objects.filter(employee=employee, date__range=(start, end)).order_by("date")
    )
    stats = {"total": len(records), "on_time": 0, "late": 0, "early": 0, "absent": 0}
    for record in records:
        if record.status == 1:
            stats["on_time"] += 1
        elif record.status == 2:
            stats["late"] += 1
        elif record.status == 3:
            stats["early"] += 1
        else:
            stats["absent"] += 1
    # 平均上班时间，让点评更有依据
    minutes = [
        record.check_in.hour * 60 + record.check_in.minute
        for record in records if record.check_in
    ]
    avg_check_in = ""
    if minutes:
        avg = sum(minutes) // len(minutes)
        avg_check_in = "%02d:%02d" % (avg // 60, avg % 60)
    salary = Salary.objects.filter(employee=employee, month=month).first()
    stats["salary_total"] = "%.2f" % salary.total if salary else None

    lines = [
        f"员工：{employee.name}（{employee.depart.title if employee.depart else '未分配部门'}）",
        f"统计月份：{month}",
        f"考勤天数：{stats['total']} 天（按时 {stats['on_time']} 次，迟到 {stats['late']} 次，"
        f"早退 {stats['early']} 次，缺勤 {stats['absent']} 次）",
    ]
    if avg_check_in:
        lines.append(f"平均上班打卡时间：{avg_check_in}")
    if salary:
        lines.append(
            f"当月薪资：基本工资 {salary.base_salary}，奖金 {salary.bonus}，"
            f"扣款 {salary.deduction}，实发 {salary.total}"
        )
    else:
        lines.append("当月薪资：暂无薪资记录")
    return stats, "\n".join(lines)


def salary_comment(request):
    """T4：对某员工某月的薪资 + 考勤数据生成一句点评或改进建议。"""
    if request.method != "POST":
        return _error("请求方式错误")
    allowed, message = check_rate(request)
    if not allowed:
        return _error(message)
    user = _current_user(request)
    if not user:
        return _error("请先登录")
    values = _payload(request, "employee_id", "month")
    month = (values.get("month") or datetime.date.today().strftime("%Y-%m")).strip()
    if not re.match(r"^\d{4}-\d{2}$", month):
        return _error("月份格式应为 YYYY-MM")

    # 数据范围校验：员工只能点评自己，管理员只能点评自己的数据范围内的人
    allowed_employees = scope_employees(user)
    employee_id = values.get("employee_id")
    if scope_of(user) == SELF:
        employee = my_employee(user)
    elif employee_id:
        employee = allowed_employees.filter(id=employee_id).first()
    else:
        employee = allowed_employees.first()
    if not employee or not allowed_employees.filter(id=employee.id).exists():
        return _error("没有可点评的员工数据，请确认数据范围内存在该员工")

    stats, data_text = _build_employee_data(employee, month)
    result = LLMClient.chat(
        build_comment_prompt(data_text),
        system=COMMENT_SYSTEM,
        temperature=0.5,
        fallback=offline_ai.review_reply(employee.name, month, stats),
    )
    return _ok(
        result,
        mode=getattr(result, "mode", "offline"),
        error=getattr(result, "error", ""),
        data_text=data_text,
        employee=employee.name,
        month=month,
        stats=stats,
    )


ai_review = salary_comment


# --------------------------------------------------------------------------- #
# T5 多轮对话
# --------------------------------------------------------------------------- #
def _answer_chat(request, question, history):
    """非流式对话核心：自我介绍 → 数据问答 → 制度检索 → 模型/兜底"""
    if any(key in question for key in IDENTITY_KEYS):
        _append_history(request, question, IDENTITY_ANSWER)
        return IDENTITY_ANSWER, "data", ""

    # 先判断是不是“查系统数据”的问题（多少员工、本月迟到几次、薪资合计…）
    # 这类问题必须查数据库，并严格套用当前账号的数据范围，不能交给模型自由发挥
    data_answer = answer_data_question(_current_user(request), question)
    if data_answer:
        _append_history(request, question, data_answer["answer"])
        return data_answer["answer"], "data", ""

    docs = search_knowledge(question, top_k=2)
    result = LLMClient.chat(
        build_chat_prompt(question, docs_to_text(docs)),
        system=CHAT_SYSTEM,
        temperature=0.7,
        history=history,
        fallback=offline_ai.chat_reply(question, history, docs),
    )
    _append_history(request, question, result)
    return result, getattr(result, "mode", "offline"), getattr(result, "error", "")


def chat_ajax(request):
    """T5：多轮对话（表单版，兼容原页面）。"""
    if request.method != "POST":
        return _error("请求方式错误")
    # 清空对话：前端传 clear=1，直接清空 session 历史后返回
    if request.POST.get("clear") == "1" or request.GET.get("clear") == "1":
        request.session[HISTORY_KEY] = []
        return _ok("对话已清空")
    allowed, message = check_rate(request)
    if not allowed:
        return _error(message)
    values = _payload(request, "question", "message")
    question, error = clean_text(values.get("question") or values.get("message"), "chat")
    if error:
        return _error(error)

    answer, mode, err = _answer_chat(request, question, _history(request))
    docs = search_knowledge(question, top_k=2) if mode != "data" else []
    sources = [{"title": d["title"], "category": d["category"]} for d in docs]
    return _ok(
        answer, mode=mode, error=err, sources=sources,
        history=_history(request), history_len=len(_history(request)),
    )


ai_chat = chat_ajax


def _stream_plain_text(request, question, text, mode="data"):
    """把已经算好的确定性答案按 SSE 逐字吐出去，保持和模型流式一样的交互体验"""
    history = _history(request)
    history.append({"role": "user", "content": question})
    _save_history(request, history)
    meta = {"meta": {"mode": mode, "sources": []}}

    def event_stream():
        yield "data: " + json.dumps(meta, ensure_ascii=False) + "\n\n"
        step = 6
        for index in range(0, len(text), step):
            piece = text[index:index + step]
            yield "data: " + json.dumps({"delta": piece}, ensure_ascii=False) + "\n\n"
            time.sleep(0.02)
        yield "data: " + json.dumps({"done": True, "answer": text}, ensure_ascii=False) + "\n\n"

    response = StreamingHttpResponse(event_stream(), content_type="text/event-stream")
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response


def ai_chat_stream(request):
    """T5：多轮对话（SSE 流式版，供全局 AI 浮窗使用）"""
    if request.method != "POST":
        return _error("请求方式错误")
    values = _payload(request, "question", "message")
    question, error = clean_text(values.get("question") or values.get("message"), "chat")
    if error:
        return _error(error)

    # 自我介绍类问题：固定回答，保证“wg”的人设稳定
    if any(key in question for key in IDENTITY_KEYS):
        return _stream_plain_text(request, question, IDENTITY_ANSWER, mode="data")

    # 数据类问题：查库算准数字，再按 SSE 逐字输出，不经过模型（避免模型编造统计结果）
    data_answer = answer_data_question(_current_user(request), question)
    if data_answer:
        return _stream_plain_text(request, question, data_answer["answer"], mode="data")

    history = _history(request)
    docs = search_knowledge(question, top_k=2)
    fallback_text = offline_ai.chat_reply(question, history, docs)
    # 流式返回前先把“用户这一问”写入历史，回答由前端在结束事件后回写
    history = history + [{"role": "user", "content": question}]
    meta = {
        "meta": {
            "mode": "llm" if LLMClient().configured else "offline",
            "sources": [{"title": d["title"], "category": d["category"]} for d in docs],
        }
    }

    def event_stream():
        yield "data: " + json.dumps(meta, ensure_ascii=False) + "\n\n"
        chunks = []
        try:
            for delta in LLMClient.chat_stream(
                build_chat_prompt(question, docs_to_text(docs)),
                system=CHAT_SYSTEM,
                history=history,
                fallback=fallback_text,
            ):
                chunks.append(delta)
                yield "data: " + json.dumps({"delta": delta}, ensure_ascii=False) + "\n\n"
        except Exception as exc:  # 兜底：流式异常也不能让前端崩
            text = f"【提示】流式输出中断：{exc}"
            chunks = [text]
            yield "data: " + json.dumps({"delta": text}, ensure_ascii=False) + "\n\n"
        yield "data: " + json.dumps(
            {"done": True, "answer": "".join(chunks)}, ensure_ascii=False
        ) + "\n\n"

    response = StreamingHttpResponse(event_stream(), content_type="text/event-stream")
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response


def ai_chat_commit(request):
    """流式输出结束后，前端把完整回答回写进会话历史"""
    if request.method != "POST":
        return _error("请求方式错误")
    values = _payload(request, "answer")
    answer = (values.get("answer") or "").strip()
    if not answer:
        return _error("回答内容为空")
    history = _history(request)
    history.append({"role": "assistant", "content": answer[:2000]})
    _save_history(request, history)
    return JsonResponse({"status": True, "history_len": len(history)})


def ai_chat_clear(request):
    """清空多轮对话历史"""
    if request.method != "POST":
        return _error("请求方式错误")
    request.session.pop(HISTORY_KEY, None)
    return JsonResponse({"status": True, "msg": "已清空对话历史", "data": "已清空对话历史"})


def ai_chat_history(request):
    """给 AI 浮窗用：读取与工作台共用的最近几轮历史"""
    if not _current_user(request):
        return _error("请先登录")
    if request.method != "GET":
        return _error("请求方式错误")
    history = _history(request)
    return JsonResponse({
        "status": True,
        "history": history[-HISTORY_LIMIT:],
        "history_len": len(history),
    })


@ensure_csrf_cookie
def ai_csrf(request):
    """浮窗在缺少 csrftoken cookie 时调用，确保之后的 POST 带得上 CSRF"""
    return JsonResponse({"status": True})
