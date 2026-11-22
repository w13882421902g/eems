"""
AI 助手的数据问答（对照参考仓库 app01/utils/data_qa.py 移植）

设计原因：
    制度知识库只能回答“公司规定是什么”，回答不了“现在有多少个员工”“本月迟到几次”。
    这类问题必须查数据库，而且要严格套用分级权限（超管=全部 / 部门管理员=本部门 / 员工=本人），
    否则 AI 就成了绕过权限看数据的后门。

约定：
    answer_data_question(user, question) -> dict | None
        命中数据类问题时返回 {"answer": 文本, "topic": 主题, "scope": 范围说明}
        判断为制度类问题（怎么扣款、有几天、流程）时返回 None，交给制度知识库流程
"""
import calendar
import datetime
import re
from decimal import Decimal, ROUND_HALF_UP

from django.db.models import Avg, Count, Sum

from app01.models import Employee
from app01.utils.scope import (
    DEPT, SELF, SUPER, my_employee, scope_attendance, scope_departments,
    scope_employees, scope_label, scope_notices, scope_of, scope_salary, scope_tasks,
)

# 出现这些词，说明问的是“规定/流程”，应该走制度知识库，而不是查数据
POLICY_WORDS = (
    "怎么扣", "怎么算", "怎么请", "怎么申", "怎么办", "怎么处理", "怎么发",
    "如何计算", "如何申请", "如何办理", "规定", "制度", "标准", "流程",
    "几天", "多久", "能不能", "可不可以", "是否允许", "政策", "条款",
    "要求", "扣多少", "手册", "条例", "办法", "须知",
)

TOPIC_KEYWORDS = {
    "profile": ("我的档案", "我的信息", "我是谁", "我的部门", "我的岗位", "我的入职"),
    # 按姓名问某个人的档案（先于“员工”匹配，避免“王俊杰的信息”被当成人数统计）
    "employee_detail": (
        "档案", "资料", "个人信息", "基本信息", "信息", "多大", "几岁",
        "手机号", "电话号码", "入职时间", "入职日期", "余额", "工龄", "性别", "年龄",
        "哪个部门", "属于哪个部门",
    ),
    "departments": ("几个部门", "哪些部门", "部门数量", "部门人数", "各部门", "每个部门"),
    "employees": ("员工", "人数", "多少人", "几个人", "总人数", "人员数量"),
    "attendance": ("考勤", "迟到", "早退", "缺勤", "旷工", "出勤", "打卡"),
    "salary": ("工资", "薪资", "薪水", "薪酬", "实发", "平均工资"),
    "tasks": ("任务", "待办", "工作安排"),
    "notices": ("公告", "通知"),
}

MONTH_RE = re.compile(r"(20\d{2})\s*[-/年]\s*(\d{1,2})")


def _target_month(question):
    """从问题里识别统计月份，默认本月"""
    today = datetime.date.today()
    if "上个月" in question or "上月" in question:
        first = today.replace(day=1)
        prev = first - datetime.timedelta(days=1)
        return prev.strftime("%Y-%m"), "上月（%s）" % prev.strftime("%Y-%m")
    found = MONTH_RE.search(question)
    if found:
        month = "%d-%02d" % (int(found.group(1)), int(found.group(2)))
        return month, "%s年%s月" % (int(found.group(1)), int(found.group(2)))
    single = re.search(r"(\d{1,2})\s*月", question)
    if single:
        month = "%d-%02d" % (today.year, int(single.group(1)))
        return month, "%d年%d月" % (today.year, int(single.group(1)))
    return today.strftime("%Y-%m"), "本月（%s）" % today.strftime("%Y-%m")


def _month_range(month):
    year, mon = (int(part) for part in month.split("-"))
    return (
        datetime.date(year, mon, 1),
        datetime.date(year, mon, calendar.monthrange(year, mon)[1]),
    )


def _money(value):
    if value is None:
        return "0.00"
    return str(Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _detect_topic(question):
    """识别数据问题主题；制度类问题直接返回 None"""
    for word in POLICY_WORDS:
        if word in question:
            return None
    for topic, words in TOPIC_KEYWORDS.items():
        for word in words:
            if word in question:
                return topic
    return None


def _named_employee(question, user):
    """
    识别问题里“点了名”的员工，且只在当前账号的数据范围内查找。
    返回 (employee, blocked_name)：
        (员工, None)      -> 命中且有权查看
        (None, "张三")    -> 问题里点了名，但不在当前数据范围内（越权）
        (None, None)      -> 问题没点名
    """
    if not question:
        return None, None
    # 1) 先在自己有权限的范围内找，长名字优先（避免“王俊”抢走“王俊杰”）
    pool = list(scope_employees(user))
    for employee in sorted(pool, key=lambda e: len(e.name or ""), reverse=True):
        if len(employee.name or "") >= 2 and employee.name in question:
            return employee, None
    # 2) 范围里没有，但库里确实有这个人：说明是越权查看
    other_names = list(
        Employee.objects.exclude(id__in=[e.id for e in pool]).values_list("name", flat=True)
    )
    for name in sorted(other_names, key=len, reverse=True):
        if len(name or "") >= 2 and name in question:
            return None, name
    return None, None


def _no_permission_message(name, user):
    return "「%s」不在你的数据范围内，无权查看其考勤、薪资和档案。\n（数据范围：%s）" % (
        name, scope_label(user),
    )


def _employee_block(user, question=""):
    scope = scope_of(user)
    queryset = scope_employees(user)
    total = queryset.count()
    if total == 0:
        return "当前你的数据范围内没有员工记录。\n（数据范围：%s）" % scope_label(user)
    lines = ["当前共有 %d 名员工（数据范围：%s）。" % (total, scope_label(user))]
    if ("名单" in question or "都有谁" in question or "哪些员工" in question) and scope in (SUPER, DEPT):
        names = [
            "%s（%s）" % (e.name, e.depart.title if e.depart else "未分配")
            for e in queryset[:10]
        ]
        lines.append("前 %d 位：%s。" % (len(names), "、".join(names)))
    if scope in (SUPER, DEPT):
        rows = (
            queryset.values("depart__title")
            .annotate(total=Count("id"))
            .order_by("-total")
        )
        parts = ["%s %d 人" % (row["depart__title"] or "未分配部门", row["total"]) for row in rows]
        lines.append("按部门分布：" + "、".join(parts))
    elif scope == SELF:
        employee = my_employee(user)
        if employee:
            lines[0] = "你的数据范围内只有你自己这 1 名员工：%s（%s）。" % (
                employee.name,
                employee.depart.title if employee.depart else "未分配部门",
            )
    lines.append("（数据来自系统数据库，按当前账号权限实时统计）")
    return "\n".join(lines)


def _department_block(user, question=""):
    rows = scope_departments(user).values("title").annotate(total=Count("employee"))
    if not rows:
        return "当前你的数据范围内没有部门记录。\n（数据范围：%s）" % scope_label(user)
    # 普通员工只看“自己所属部门”，不给人数（人数属于管理视角的统计）
    if scope_of(user) == SELF:
        return "你所属的部门：%s。\n（数据范围：%s）" % (
            "、".join(row["title"] for row in rows), scope_label(user))
    lines = ["当前可见 %d 个部门（数据范围：%s）：" % (len(rows), scope_label(user))]
    lines.append("、".join("%s %d 人" % (row["title"], row["total"]) for row in rows))
    return "\n".join(lines)


def _has_explicit_month(question):
    return (
        "上个月" in question or "上月" in question
        or bool(MONTH_RE.search(question))
        or bool(re.search(r"(\d{1,2})\s*月", question))
    )


def _is_personal(question):
    """问的是“我自己的”数据：哪怕管理员原本能看全公司，也只查本人"""
    return any(word in question for word in ("我的", "本人", "我自己", "我本月", "我这个月", "我上个月"))


def _attendance_block(user, question):
    month, month_text = _target_month(question)
    start, end = _month_range(month)
    personal = _is_personal(question)
    target, blocked = _named_employee(question, user)
    if blocked:
        return _no_permission_message(blocked, user)
    records = scope_attendance(user)
    if target:
        records = records.filter(employee=target)
    elif personal:
        employee = my_employee(user)
        if not employee:
            return "你的账号还没有绑定员工档案，查不到你本人的考勤；请联系管理员在「用户管理」里绑定。"
        records = records.filter(employee=employee)
    base = records  # 已按权限（或“仅本人”）过滤好的底表
    records = base.filter(date__range=(start, end))
    total = records.count()
    # 没明确说时间、且本月还没录入考勤时，自动回退到“最近有记录的月份”，避免答“没有记录”让人误以为系统没数据
    if total == 0 and not _has_explicit_month(question):
        latest = base.order_by("-date").values_list("date", flat=True).first()
        if latest:
            start = latest.replace(day=1)
            end = latest.replace(day=calendar.monthrange(latest.year, latest.month)[1])
            records = base.filter(date__range=(start, end))
            total = records.count()
            month_text = "最近有记录的月份（%s）" % latest.strftime("%Y-%m")
    if total == 0:
        if target:
            return "%s在%s没有查到考勤记录。\n（数据范围：%s）" % (
                target.name, month_text, scope_label(user))
        return "%s没有查到考勤记录。\n（数据范围：%s）" % (month_text, scope_label(user))
    counts = {row["status"]: row["total"] for row in records.values("status").annotate(total=Count("id"))}
    on_time = counts.get(1, 0)
    late = counts.get(2, 0)
    early = counts.get(3, 0)
    absent = counts.get(4, 0)
    # 点名查看某个人的考勤：给逐人明细，而不是全公司汇总
    if target:
        lines = ["%s在%s考勤共 %d 条：按时 %d、迟到 %d、早退 %d、缺勤 %d。" % (
            target.name, month_text, total, on_time, late, early, absent)]
        late_rows = records.filter(status=2).order_by("-date")[:5]
        if late_rows:
            lines.append("迟到明细：" + "；".join(
                "%s %s" % (
                    r.date.strftime("%m-%d"),
                    r.check_in.strftime("%H:%M 打卡") if r.check_in else "未打卡",
                ) for r in late_rows
            ))
        absent_rows = records.filter(status=4).order_by("-date")[:5]
        if absent_rows:
            lines.append("缺勤日期：" + "、".join(r.date.strftime("%m-%d") for r in absent_rows))
        lines.append("（数据范围：%s；统计口径：系统考勤表）" % scope_label(user))
        return "\n".join(lines)
    if "迟到" in question and "早退" not in question and "缺勤" not in question:
        people = records.filter(status=2).values("employee_id").distinct().count()
        head = "%s迟到 %d 次，涉及 %d 人。" % (month_text, late, people)
    elif "缺勤" in question or "旷工" in question:
        people = records.filter(status=4).values("employee_id").distinct().count()
        head = "%s缺勤（旷工）%d 次，涉及 %d 人。" % (month_text, absent, people)
    elif "早退" in question:
        people = records.filter(status=3).values("employee_id").distinct().count()
        head = "%s早退 %d 次，涉及 %d 人。" % (month_text, early, people)
    else:
        head = "%s考勤共 %d 条：按时 %d、迟到 %d、早退 %d、缺勤 %d。" % (
            month_text, total, on_time, late, early, absent,
        )
    return head + "\n（数据范围：%s；统计口径：系统考勤表）" % scope_label(user)


def _salary_block(user, question):
    month, month_text = _target_month(question)
    personal = _is_personal(question)
    target, blocked = _named_employee(question, user)
    if blocked:
        return _no_permission_message(blocked, user)
    base = scope_salary(user)
    if target:
        base = base.filter(employee=target)
    elif personal:
        employee = my_employee(user)
        if not employee:
            return "你的账号还没有绑定员工档案，查不到你本人的薪资；请联系管理员在「用户管理」里绑定。"
        base = base.filter(employee=employee)
    records = base.filter(month=month)
    total = records.count()
    if total == 0 and not _has_explicit_month(question):
        latest = base.order_by("-month").values_list("month", flat=True).first()
        if latest:
            month = latest
            records = base.filter(month=month)
            total = records.count()
            month_text = "最近有记录的月份（%s）" % month
    if total == 0:
        if target:
            return "没有查到%s的薪资记录。\n（数据范围：%s）" % (target.name, scope_label(user))
        return "%s没有查到薪资记录。\n（数据范围：%s）" % (month_text, scope_label(user))
    sums = records.aggregate(sum_total=Sum("total"), avg_total=Avg("total"))
    # 单人明细：点名的人 / 问“我的” / 员工本人
    if target or scope_of(user) == SELF or personal:
        row = records.first()
        if target:
            head = "%s在%s的实发工资是 %s 元（基本 %s + 奖金 %s - 扣款 %s）。" % (
                target.name, month_text, _money(row.total), _money(row.base_salary),
                _money(row.bonus), _money(row.deduction),
            )
        else:
            head = "你%s的实发工资是 %s 元（基本 %s + 奖金 %s - 扣款 %s）。" % (
                month_text, _money(row.total), _money(row.base_salary),
                _money(row.bonus), _money(row.deduction),
            )
        history_rows = base.exclude(month=month).order_by("-month")[:3]
        lines = [head]
        if history_rows:
            lines.append("近几个月：" + "、".join(
                "%s 实发 %s 元" % (r.month, _money(r.total)) for r in history_rows))
        lines.append("（数据范围：%s；统计口径：系统薪资表）" % scope_label(user))
        return "\n".join(lines)
    return "%s薪资记录 %d 条，实发合计 %s 元，人均 %s 元。\n（数据范围：%s；统计口径：系统薪资表）" % (
        month_text, total, _money(sums["sum_total"]), _money(sums["avg_total"]), scope_label(user),
    )


def _task_block(user):
    queryset = scope_tasks(user).select_related("leader")
    total = queryset.count()
    if total == 0:
        return "当前你的数据范围内没有任务记录。\n（数据范围：%s）" % scope_label(user)
    titles = list(queryset.values_list("title", flat=True)[:3])
    return "当前任务共 %d 个，最近的 %d 个是：%s。\n（数据范围：%s）" % (
        total, len(titles), "、".join(titles), scope_label(user),
    )


def _notice_block(user):
    notices = scope_notices(user)[:3]
    total = scope_notices(user).count()
    if not total:
        return "当前系统里还没有公告。"
    return "当前共 %d 条公告，最新 3 条：%s。" % (
        total, "、".join(notice.title for notice in notices),
    )


def _profile_block(user):
    employee = my_employee(user)
    if not employee:
        return "你是系统管理员账号「%s」，当前还没有绑定员工档案（可在「用户管理」里绑定后查询本人考勤和薪资）。" % user.username
    return "你是 %s，所属部门：%s，入职日期：%s，联系电话：%s。\n（来源：你的员工档案）" % (
        employee.name,
        employee.depart.title if employee.depart else "未分配部门",
        employee.entry_date.strftime("%Y-%m-%d") if employee.entry_date else "未登记",
        employee.mobile or "未登记",
    )


def _employee_detail_block(user, question):
    """按姓名查员工档案；没点名就给当前可见的员工名单"""
    target, blocked = _named_employee(question, user)
    if blocked:
        return _no_permission_message(blocked, user)
    if target:
        lines = [
            "「%s」的档案信息：" % target.name,
            "· 部门：%s" % (target.depart.title if target.depart else "未分配部门"),
            "· 性别 / 年龄：%s / %d 岁" % (target.get_gender_display(), target.age),
            "· 入职日期：%s" % (
                target.entry_date.strftime("%Y-%m-%d") if target.entry_date else "未登记"),
            "· 手机号：%s" % (target.mobile or "未登记"),
            "· 账户余额：%s 元" % _money(target.balance),
            "· 登录账号：%s" % (target.user.username if target.user_id else "未绑定"),
        ]
        return "\n".join(lines) + "\n（数据范围：%s；来源：系统员工档案）" % scope_label(user)
    pool = scope_employees(user)
    total = pool.count()
    if total == 0:
        return "当前你的数据范围内没有员工档案。\n（数据范围：%s）" % scope_label(user)
    names = [
        "%s（%s）" % (e.name, e.depart.title if e.depart else "未分配")
        for e in pool[:10]
    ]
    more = "，仅列出前 10 位" if total > 10 else ""
    return "当前可见 %d 名员工的档案%s：%s。\n（数据范围：%s；来源：系统员工档案）" % (
        total, more, "、".join(names), scope_label(user),
    )


BUILDERS = {
    "profile": _profile_block,
    "employee_detail": _employee_detail_block,
    "departments": _department_block,
    "employees": _employee_block,
    "attendance": _attendance_block,
    "salary": _salary_block,
    "tasks": _task_block,
    "notices": _notice_block,
}


def answer_data_question(user, question):
    """命中数据类问题就返回答案字典，否则返回 None（继续走制度知识库）"""
    if not user or not question:
        return None
    topic = _detect_topic(question)
    if not topic:
        return None
    builder = BUILDERS.get(topic)
    if not builder:
        return None
    if topic in ("attendance", "salary", "employee_detail", "employees", "departments"):
        answer = builder(user, question)
    else:
        answer = builder(user)
    return {
        "answer": answer,
        "topic": topic,
        "scope": scope_label(user),
    }
