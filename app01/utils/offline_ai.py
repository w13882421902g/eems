"""
规则兜底生成器（对照参考仓库 app01/utils/offline_ai.py 移植）

作用：没有配置大模型 API Key、或网络/接口异常时，仍然能给出结构完整的内容，
保证页面不报错、演示现场可以完整走通闭环。输出与正常回答格式一致，不额外加标注。
"""


def chat_reply(question, history=None, kb_docs=None):
    """多轮对话兜底：有关键词能命中制度库就答制度，否则给出通用引导"""
    q = question.strip()
    if any(k in q for k in ("你是谁", "你叫什么", "你的名字", "介绍一下你", "你能做什么")):
        return (
            "我是wg，这个系统的 AI 助手。制度、考勤、薪资、员工信息都能问我；"
            "超出你的数据范围或没有依据的，我会直接说不知道。"
        )
    lines = []
    topic = _detect_topic(question)
    if kb_docs:
        first = kb_docs[0]
        lines.append(f"根据制度库《{first['title']}》：")
        lines.append(first["content"].strip())
        if topic:
            lines.append(
                f"针对你问的“{topic}”，上面这条制度是最相关的依据，如需更细的规定可以继续追问。"
            )
    else:
        lines.append("关于“%s”，我暂时没有在制度库里找到对应条款。" % question.strip())
        lines.append("你可以问我：请假怎么审批、报销需要哪些材料、考勤迟到怎么算、某位员工本月表现如何。")
    if history:
        lines.append("如果还要接着上面的话题问，直接说就行。")
    return "\n".join(lines)


def jd_reply(job_title, department="", level="", extra=""):
    """招聘 JD 兜底：按岗位名称套用结构化模板"""
    job_title = job_title.strip() or "未命名岗位"
    department = department.strip() or "用人部门"
    level = level.strip() or "中级"
    lines = [
        f"# {job_title}（{department} / {level}）",
        "",
        "## 一、岗位职责",
        f"1. 负责{department}{job_title}相关的日常业务执行与推进；",
        "2. 参与部门内部协作，按时交付任务并对结果负责；",
        f"3. 完成上级安排的其他与{job_title}相关的工作。",
        "",
        "## 二、任职要求",
        f"1. 学历：大专及以上，{job_title}相关专业优先；",
        f"2. 经验：具备{level}岗位所需的相关工作经验，能独立完成本职工作；",
        "3. 能力：沟通表达清晰、责任心强，具备团队协作意识；",
        "4. 加分项：有同行业经验或相关职业资格证书。",
        "",
        "## 三、薪资福利",
        "1. 薪资：面议（按能力与经验定级，结构为基本工资 + 绩效奖金）；",
        "2. 福利：五险一金、带薪年假、节日福利、定期团建；",
        "3. 发展：提供岗位技能培训与晋升通道。",
    ]
    if extra.strip():
        lines += ["", "## 四、补充说明", extra.strip()]
    return "\n".join(lines)


def kb_reply(question, docs):
    """制度问答兜底：只依据检索到的制度条目作答，检索不到就明确答不知道"""
    if not docs:
        return (
            "不知道。制度知识库中没有检索到与“" + question.strip() + "”相关的条款，"
            "建议补充制度条目或咨询人事部门。"
        )
    lines = ["以下内容依据制度库中检索到的条款："]
    for index, doc in enumerate(docs, start=1):
        content = doc["content"].strip()
        lines.append(f"{index}. 《{doc['title']}》（{doc['category']}）：{content}")
    lines.append("以上内容均来自本地制度库；库中没有的内容我不会编造。")
    return "\n".join(lines)


def review_reply(employee_name, month, stats):
    """数据点评兜底：按考勤/薪资统计规则给出一句点评 + 改进建议"""
    late = stats.get("late", 0)
    absent = stats.get("absent", 0)
    early = stats.get("early", 0)
    on_time = stats.get("on_time", 0)
    total = stats.get("total", 0)
    salary_total = stats.get("salary_total")
    if total == 0:
        return (
            f"{employee_name}在 {month} 没有考勤记录，"
            "暂时无法点评，建议先补录考勤数据。"
        )
    comment = []
    if absent == 0 and late == 0 and early == 0:
        comment.append(
            f"{employee_name} {month} 共 {total} 天考勤全部按时，出勤纪律良好，状态稳定。"
        )
        advice = "建议保持当前出勤节奏，可以适当安排更有挑战性的任务。"
    else:
        comment.append(
            f"{employee_name} {month} 共 {total} 天考勤，按时 {on_time} 次、"
            f"迟到 {late} 次、早退 {early} 次、缺勤 {absent} 次。"
        )
        if late:
            advice = f"迟到 {late} 次偏多，建议提前 10 分钟出门并设置双重闹钟，避免影响团队晨会。"
        elif absent:
            advice = f"缺勤 {absent} 次需要关注，建议提前走请假流程并与主管同步工作交接。"
        else:
            advice = f"早退 {early} 次，建议把手头工作安排在上班时间完成，确需早退提前报备。"
    if salary_total is not None:
        comment.append(f"当月实发工资 {salary_total} 元。")
    return "".join(comment) + "改进建议：" + advice


def _detect_topic(question):
    """粗略识别问题主题，用于兜底话术"""
    topics = {
        "请假": "请假", "年假": "请假", "调休": "请假",
        "报销": "报销", "发票": "报销",
        "考勤": "考勤", "迟到": "考勤", "打卡": "考勤",
        "工资": "薪资", "薪资": "薪资", "奖金": "薪资",
        "晋升": "晋升", "转正": "晋升",
        "离职": "离职", "培训": "培训",
    }
    for keyword, topic in topics.items():
        if keyword in question:
            return topic
    return ""
