"""
页面级冒烟测试：验证新增的首页、分级权限、AI 接口在真实数据库上不报错。

只读为主；为覆盖“普通员工（self）”视角，会临时创建一个测试账号并绑定到某位员工，
测试结束（无论成功失败）都会删除该账号并解除绑定，不留下数据。
"""
import json
import os
import sys
import time

import django

# 允许直接 python scripts/xxx.py 运行：把项目根目录加入模块搜索路径
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "hrms.settings")
django.setup()

from django.test import Client  # noqa: E402

from app01.models import Employee, User  # noqa: E402

RESULTS = []


def record(name, ok, detail=""):
    RESULTS.append((name, ok, detail))
    print(("PASS " if ok else "FAIL ") + name + (("  <- " + detail) if detail and not ok else ""))


def login(client, user):
    session = client.session
    session["user_id"] = user.id
    session["user_name"] = user.username
    session.save()


def get(client, url, expect=200):
    resp = client.get(url)
    return resp.status_code == expect, resp


def post_ai(client, url, data):
    """AI 接口有 1 秒频率限制，连续调用前先等一下，避免测试自己把自己限流"""
    time.sleep(1.2)
    return client.post(url, data)


def main():
    super_user = User.objects.filter(is_superuser=True).first() or User.objects.filter(username="粮食猪").first()
    dept_user = User.objects.filter(employee__isnull=True).first()
    # 找出一个部门负责人账号（demo_data 里 6 个部门管理员）
    leader = (
        User.objects.filter(departments__isnull=False).distinct().first()
        if hasattr(User, "departments")
        else None
    )
    if leader is None:
        from app01.models import Department

        leader = Department.objects.exclude(leader__isnull=True).first().leader
    employee = Employee.objects.filter(name="张伟").first() or Employee.objects.first()

    temp_user = None
    original_binding = employee.user_id
    try:
        # ---------- 超级管理员 ----------
        client = Client()
        login(client, super_user)
        for url in ["/home/", "/employee/list/", "/department_list_placeholder"]:
            if url == "/department_list_placeholder":
                continue
            ok, resp = get(client, url)
            record("super GET " + url, ok, str(resp.status_code))
        for url in ["/depart/list/", "/attendance/list/", "/salary/list/", "/notice/list/",
                    "/task/list/", "/chart/", "/user_manage/list/", "/role/list/", "/ai/assistant/",
                    "/ai/chat/history/", "/order/list/"]:
            ok, resp = get(client, url)
            record("super GET " + url, ok, str(resp.status_code))

        resp = post_ai(client, "/ai/chat/", {"question": "公司现在有多少员工？"})
        body = resp.json()
        record("super AI 数据问答", resp.status_code == 200 and body.get("status")
               and "员工" in body.get("data", ""), body.get("data", "")[:80])

        resp = post_ai(client, "/ai/knowledge/qa/", {"question": "年假有几天？"})
        body = resp.json()
        record("super AI 制度问答", resp.status_code == 200 and body.get("status"),
               body.get("data", "")[:80])

        resp = client.post("/ai/chat/stream/", {"message": "迟到了会扣钱吗"},
                           content_type="application/json")
        text = b"".join(resp.streaming_content).decode("utf-8", "ignore")
        record("super AI 流式回答", resp.status_code == 200 and "delta" in text, text[:80])

        # ---------- 部门管理员 ----------
        client = Client()
        login(client, leader)
        ok, resp = get(client, "/home/")
        record("dept GET /home/", ok, str(resp.status_code))
        ok, resp = get(client, "/employee/list/")
        record("dept GET /employee/list/", ok, str(resp.status_code))
        resp = client.get("/user_manage/list/")
        record("dept 被拦截用户管理", resp.status_code == 403, str(resp.status_code))
        resp = post_ai(client, "/ai/chat/", {"question": "本月有多少人迟到？"})
        body = resp.json()
        record("dept AI 考勤问答", resp.status_code == 200 and body.get("status"),
               body.get("data", "")[:80])

        # ---------- 普通员工（self） ----------
        temp_user = User.objects.create(username="冒烟测试用户", is_active=True)
        temp_user.set_password("123456")
        temp_user.save()
        employee.user = temp_user
        employee.save(update_fields=["user"])
        client = Client()
        login(client, temp_user)
        ok, resp = get(client, "/home/")
        record("self GET /home/", ok, str(resp.status_code))
        ok, resp = get(client, "/attendance/list/")
        record("self GET /attendance/list/", ok, str(resp.status_code))
        resp = client.post("/employee/delete/" + str(employee.id) + "/")
        record("self 被拦截删员工", resp.status_code == 403, str(resp.status_code))
        resp = post_ai(client, "/ai/chat/", {"question": "我的工资是多少？"})
        body = resp.json()
        salary_text = body.get("data", "")
        record("self AI 本人薪资",
               body.get("status") and ("实发工资" in salary_text or "没有查到薪资记录" in salary_text),
               salary_text[:80])
        resp = post_ai(client, "/ai/chat/", {"question": "公司现在有多少员工？"})
        body = resp.json()
        count_text = body.get("data", "")
        record("self AI 人数受限",
               ("只有你自己这 1 名员工" in count_text) or ("没有员工记录" in count_text),
               count_text[:80])
    finally:
        if temp_user is not None:
            employee.user_id = original_binding
            employee.save(update_fields=["user"])
            temp_user.delete()

    failed = [row for row in RESULTS if not row[1]]
    print("\n共 %d 项，失败 %d 项" % (len(RESULTS), len(failed)))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
