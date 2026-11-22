"""
回归测试：覆盖本次修复的缺陷，防止以后改代码时再次退化。

运行方式：
    python manage.py test app01 -v 2
"""
from django.test import TestCase

from app01.forms import SalaryModelForm, AttendanceModelForm
from app01.models import (
    User, Department, Employee, Attendance, Salary, Notice,
)


class BaseCase(TestCase):
    """公共测试数据"""

    def setUp(self):
        self.admin = User.objects.create_superuser(
            username="admin", password="abc12345", email="admin@example.com"
        )
        self.normal = User.objects.create_user(username="staff", password="abc12345")
        self.dept = Department.objects.create(title="技术部", leader=self.admin)
        self.emp = Employee.objects.create(
            name="张三", age=25, gender=1, balance=0,
            entry_date="2026-01-01", mobile="13800000001", depart=self.dept,
        )

    def login(self, user=None):
        """按项目现有机制：session 里放 user_id"""
        user = user or self.admin
        session = self.client.session
        session["user_id"] = user.id
        session["user_name"] = user.username
        session.save()


class StaticAccessTests(BaseCase):
    def test_static_not_redirected_to_login(self):
        """静态资源不能被登录中间件拦截，否则登录页会失去样式"""
        resp = self.client.get("/static/css/layout.css")
        self.assertNotEqual(resp.status_code, 302)
        self.assertNotIn("/login/", resp.get("Location", ""))

    def test_media_not_redirected_to_login(self):
        resp = self.client.get("/media/avatar/demo.png")
        self.assertNotEqual(resp.status_code, 302)

    def test_protected_page_redirects_when_anonymous(self):
        resp = self.client.get("/employee/list/")
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp["Location"], "/login/")


class LoginTests(BaseCase):
    def setUp(self):
        super().setUp()
        session = self.client.session
        session["image_code"] = "ABCDE"
        session.save()

    def test_captcha_is_single_use(self):
        """验证码用过即失效，不能被重放"""
        data = {"username": "admin", "password": "abc12345", "img_code": "ABCDE"}
        first = self.client.post("/login/", data)
        self.assertEqual(first.status_code, 302)  # 登录成功

        # 服务端在首次校验时已 pop 掉该验证码，再次提交同一码应判为验证码错误
        second = self.client.post("/login/", {"username": "admin", "password": "abc12345",
                                              "img_code": "ABCDE"})
        self.assertEqual(second.status_code, 200)
        self.assertIn("验证码错误", second.content.decode())

    def test_inactive_user_cannot_login(self):
        self.normal.is_active = False
        self.normal.save()
        session = self.client.session
        session["image_code"] = "ABCDE"
        session.save()
        resp = self.client.post("/login/", {"username": "staff", "password": "abc12345",
                                            "img_code": "ABCDE"})
        self.assertEqual(resp.status_code, 200)
        self.assertIn("账号已停用", resp.content.decode())
        self.assertNotIn("user_id", self.client.session)


class PermissionTests(BaseCase):
    def test_normal_user_forbidden_on_user_manage(self):
        self.login(self.normal)
        self.assertEqual(self.client.get("/user_manage/list/").status_code, 403)
        self.assertEqual(self.client.get("/role/list/").status_code, 403)

    def test_normal_user_cannot_delete_user(self):
        self.login(self.normal)
        resp = self.client.post(f"/user_manage/delete/{self.admin.pk}/")
        self.assertEqual(resp.status_code, 403)
        self.assertTrue(User.objects.filter(pk=self.admin.pk).exists())

    def test_normal_user_cannot_escalate_self(self):
        self.login(self.normal)
        resp = self.client.post(
            f"/user_manage/edit/{self.normal.pk}/",
            {"username": "staff", "email": "", "is_superuser": "on", "is_active": "on", "roles": []},
        )
        self.assertEqual(resp.status_code, 403)
        self.normal.refresh_from_db()
        self.assertFalse(self.normal.is_superuser)

    def test_superuser_can_open_user_manage(self):
        self.login(self.admin)
        self.assertEqual(self.client.get("/user_manage/list/").status_code, 200)
        self.assertEqual(self.client.get("/role/list/").status_code, 200)


class DeleteMethodTests(BaseCase):
    def test_delete_requires_post(self):
        self.login(self.admin)
        Notice.objects.create(title="通知", content="内容", publisher=self.admin)
        notice = Notice.objects.get(title="通知")

        self.assertEqual(self.client.get(f"/notice/delete/{notice.pk}/").status_code, 405)
        self.assertTrue(Notice.objects.filter(pk=notice.pk).exists())

        resp = self.client.post(f"/notice/delete/{notice.pk}/")
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(Notice.objects.filter(pk=notice.pk).exists())

    def test_department_delete_requires_post(self):
        self.login(self.admin)
        d = Department.objects.create(title="待删部门")
        self.assertEqual(self.client.get(f"/depart/delete/{d.pk}/").status_code, 405)
        self.assertEqual(self.client.post(f"/depart/delete/{d.pk}/").status_code, 302)
        self.assertFalse(Department.objects.filter(pk=d.pk).exists())

    def test_task_ajax_rejects_get(self):
        self.login(self.admin)
        resp = self.client.get("/task/add/ajax/")
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.json()["status"])


class DataConsistencyTests(BaseCase):
    def test_duplicate_salary_same_month_rejected(self):
        Salary.objects.create(employee=self.emp, month="2026-10", base_salary=8000, total=8000)
        form = SalaryModelForm(data={"employee": self.emp.pk, "month": "2026-10",
                                     "base_salary": 8000, "bonus": 0, "deduction": 0})
        self.assertFalse(form.is_valid())
        self.assertIn("__all__", form.errors)  # 唯一约束报在整表校验上

    def test_duplicate_attendance_same_date_rejected(self):
        Attendance.objects.create(employee=self.emp, date="2026-10-01", status=1)
        form = AttendanceModelForm(data={"employee": self.emp.pk, "date": "2026-10-01",
                                         "check_in": "09:00", "check_out": "18:00"})
        self.assertFalse(form.is_valid())
        self.assertIn("__all__", form.errors)

    def test_salary_total_auto_computed(self):
        salary = Salary.objects.create(employee=self.emp, month="2026-11",
                                       base_salary=8000, bonus=500, deduction=200)
        from decimal import Decimal
        self.assertEqual(salary.total, Decimal("8300"))

    def test_employee_pagination_is_stable(self):
        self.login(self.admin)
        for i in range(10):
            Employee.objects.create(name=f"员工{i}", age=30, gender=1, balance=0,
                                    entry_date="2026-01-01", mobile=f"139000000{i:02d}",
                                    depart=self.dept)
        page1 = self.client.get("/employee/list/?page=1")
        page2 = self.client.get("/employee/list/?page=2")
        ids1 = {e.id for e in page1.context["page_obj"].object_list}
        ids2 = {e.id for e in page2.context["page_obj"].object_list}
        self.assertEqual(len(ids1 & ids2), 0, "第一页与第二页出现重复记录")

    def test_invalid_filter_param_does_not_500(self):
        self.login(self.admin)
        resp = self.client.get("/employee/list/?depart_id=abc")
        self.assertEqual(resp.status_code, 200)
        resp = self.client.get("/salary/list/?employee_id=abc")
        self.assertEqual(resp.status_code, 200)

class CsrfTests(BaseCase):
    """POST 接口必须校验 CSRF 令牌"""

    def setUp(self):
        super().setUp()
        self.c = self.client_class(enforce_csrf_checks=True)
        session = self.c.session
        session["user_id"] = self.admin.id
        session["user_name"] = self.admin.username
        session.save()

    def test_task_ajax_requires_csrf(self):
        resp = self.c.post("/task/add/ajax/", {"level": 1, "title": "无令牌任务",
                                               "detail": "", "leader": self.admin.pk})
        self.assertEqual(resp.status_code, 403)

    def test_delete_requires_csrf(self):
        d = Department.objects.create(title="CSRF部门")
        resp = self.c.post(f"/depart/delete/{d.pk}/")
        self.assertEqual(resp.status_code, 403)
        self.assertTrue(Department.objects.filter(pk=d.pk).exists())
