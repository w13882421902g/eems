"""
回归测试：覆盖本次修复/新增的功能，防止以后改代码时再次退化。

运行方式：
    python manage.py test app01 -v 2
"""
import io

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from app01.forms import SalaryModelForm, AttendanceModelForm
from app01.models import (
    User, Department, Employee, Attendance, Salary, Notice, Task, Order,
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


class PaginationTests(BaseCase):
    """通用分页组件：页码合法性、链接保留查询参数"""

    def test_department_list_paginates(self):
        self.login(self.admin)
        for i in range(15):
            Department.objects.create(title=f"分页部门{i}")
        # setUp 已建 1 个“技术部”，共 16 条：第 1 页 10 条、第 2 页 6 条
        resp = self.client.get("/depart/list/?page=2")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context["total_count"], 16)
        self.assertEqual(len(resp.context["page_queryset"]), 6)

    def test_page_string_keeps_other_query(self):
        self.login(self.admin)
        for i in range(25):
            Department.objects.create(title=f"链接部门{i}")
        # 26 条 → 3 页，第 2 页应能看到“第 3 页”的链接
        resp = self.client.get("/depart/list/?page=2&keyword=abc")
        page_html = resp.context["page_string"]
        self.assertIn("keyword=abc", page_html)
        self.assertIn("page=3", page_html)

    def test_invalid_page_number_falls_back(self):
        self.login(self.admin)
        for i in range(15):
            Department.objects.create(title=f"兜底部门{i}")
        # 字母页码按第 1 页处理；超大页码回退到最后一页，都不能 500
        self.assertEqual(self.client.get("/depart/list/?page=abc").status_code, 200)
        resp = self.client.get("/depart/list/?page=999")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.context["page_queryset"]), 6)   # 回退到第 2 页
        self.assertIn("尾页(2)", resp.context["page_string"])

    def test_task_list_paginates(self):
        self.login(self.admin)
        for i in range(13):
            Task.objects.create(title=f"任务{i}", level=2, leader=self.admin)
        resp = self.client.get("/task/list/?page=2")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context["total_count"], 13)
        self.assertEqual(len(resp.context["page_queryset"]), 3)


class DepartmentImportTests(BaseCase):
    """Excel 批量导入：去重、空行、数字单元格、非法文件"""

    @staticmethod
    def _make_excel(rows):
        """在内存里生成 xlsx，不落盘；第一行当表头。"""
        from openpyxl import Workbook
        workbook = Workbook()
        sheet = workbook.active
        sheet.append(["部门名称"])
        for row in rows:
            sheet.append([row])
        buffer = io.BytesIO()
        workbook.save(buffer)
        buffer.seek(0)
        return buffer

    def test_import_creates_and_skips_duplicates(self):
        self.login(self.admin)
        # setUp 里已有 1 个“技术部”，导入文件里再出现两次，都应被跳过

        rows = ["技术部", "市场部", "", 1001, "技术部"]
        buffer = self._make_excel(rows)
        upload = SimpleUploadedFile(
            "depart.xlsx", buffer.read(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        resp = self.client.post("/depart/multi/", {"exc": upload}, follow=True)
        self.assertEqual(resp.status_code, 200)

        titles = set(Department.objects.values_list("title", flat=True))
        self.assertIn("市场部", titles)
        self.assertIn("1001", titles)                  # 数字单元格不能变成 "1001.0"
        self.assertEqual(Department.objects.filter(title="技术部").count(), 1)
        self.assertEqual(Department.objects.count(), 3)  # 技术部 + 市场部 + 1001

    def test_reject_non_excel_file(self):
        self.login(self.admin)
        before = Department.objects.count()
        upload = SimpleUploadedFile("depart.txt", b"not an excel", content_type="text/plain")
        self.client.post("/depart/multi/", {"exc": upload})
        self.assertEqual(Department.objects.count(), before)

    def test_reject_missing_file(self):
        self.login(self.admin)
        resp = self.client.post("/depart/multi/", {})
        self.assertEqual(resp.status_code, 302)        # 跳回列表页并提示，不 500


class OrderTests(BaseCase):
    """订单模块：新增/编辑/详情/删除 + 后端生成订单号与管理员"""

    def setUp(self):
        super().setUp()
        self.login(self.admin)

    def test_add_order(self):
        resp = self.client.post("/order/add/", {"title": "办公椅", "price": 199, "status": 2})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["status"])
        order = Order.objects.get(title="办公椅")
        self.assertEqual(order.admin_id, self.admin.id)      # 管理员取当前登录人
        self.assertEqual(len(order.oid), 18)                 # 14 位时间戳 + 4 位随机数
        self.assertTrue(order.oid.isdigit())

    def test_add_order_invalid_price(self):
        resp = self.client.post("/order/add/", {"title": "白送", "price": 0, "status": 1})
        self.assertFalse(resp.json()["status"])
        self.assertIn("price", resp.json()["error"])
        self.assertEqual(Order.objects.count(), 0)

    def test_add_order_rejects_get(self):
        self.assertEqual(self.client.get("/order/add/").status_code, 405)

    def test_detail_and_edit(self):
        order = Order.objects.create(oid="202611200000001234", title="旧名称", price=10,
                                     status=1, admin=self.admin)

        detail = self.client.get("/order/detail/?uid=%d" % order.id).json()
        self.assertTrue(detail["status"])
        self.assertEqual(detail["data"]["title"], "旧名称")

        resp = self.client.post("/order/edit/?uid=%d" % order.id,
                                {"title": "新名称", "price": 88, "status": 2})
        self.assertTrue(resp.json()["status"])
        order.refresh_from_db()
        self.assertEqual(order.title, "新名称")
        self.assertEqual(order.price, 88)
        self.assertEqual(order.status, 2)
        self.assertEqual(order.oid, "202611200000001234")    # 订单号不会被前端改掉

    def test_detail_params_safe(self):
        """非法 uid 不能抛 500（filter(id='abc') 会 ValueError）"""
        self.assertEqual(self.client.get("/order/detail/?uid=abc").json()["status"], False)
        self.assertEqual(self.client.get("/order/detail/").json()["status"], False)
        self.assertEqual(self.client.get("/order/detail/?uid=999").json()["status"], False)

    def test_delete_requires_post(self):
        order = Order.objects.create(oid="202611200000005678", title="待删", price=1,
                                     status=1, admin=self.admin)
        self.assertEqual(self.client.get("/order/delete/?uid=%d" % order.id).status_code, 405)
        self.assertTrue(Order.objects.filter(pk=order.pk).exists())

        resp = self.client.post("/order/delete/", {"uid": order.id})
        self.assertTrue(resp.json()["status"])
        self.assertFalse(Order.objects.filter(pk=order.pk).exists())

    def test_delete_missing_order(self):
        resp = self.client.post("/order/delete/", {"uid": 999})
        self.assertFalse(resp.json()["status"])


class OrderCsrfTests(BaseCase):
    """订单 Ajax 接口必须校验 CSRF（讲义示例用了 csrf_exempt，本项目保留校验）"""

    def setUp(self):
        super().setUp()
        self.c = self.client_class(enforce_csrf_checks=True)
        session = self.c.session
        session["user_id"] = self.admin.id
        session["user_name"] = self.admin.username
        session.save()

    def test_add_order_requires_csrf(self):
        resp = self.c.post("/order/add/", {"title": "无令牌", "price": 10, "status": 1})
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(Order.objects.count(), 0)


class PageRenderTests(BaseCase):
    """页面冒烟：模板语法、字段渲染、表单混入类都不能让页面 500"""

    def setUp(self):
        super().setUp()
        self.login(self.admin)

    def test_order_list_renders(self):
        Order.objects.create(oid="202611200000009999", title="示例订单", price=50,
                             status=1, admin=self.admin)
        resp = self.client.get("/order/list/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "订单列表")
        self.assertContains(resp, "示例订单")

    def test_change_pages_render(self):
        task = Task.objects.create(title="渲染任务", level=1, leader=self.admin)
        pages = [
            "/depart/add/",
            f"/depart/edit/{self.dept.pk}/",
            "/employee/add/",
            f"/employee/edit/{self.emp.pk}/",
            "/attendance/add/",
            "/salary/add/",
            "/notice/add/",
            "/task/list/",
            f"/task/delete/{task.pk}/",   # 只接受 POST，GET 应为 405
            "/user_manage/add/",
            "/role/add/",
        ]
        for url in pages:
            resp = self.client.get(url)
            if url.endswith("/delete/%d/" % task.pk):
                self.assertEqual(resp.status_code, 405)
            else:
                self.assertEqual(resp.status_code, 200, msg=f"{url} 渲染失败")

    def test_login_page_renders(self):
        self.client.get("/logout/")
        self.assertEqual(self.client.get("/login/").status_code, 200)


class ChartBarTests(BaseCase):
    """部门薪资柱状图接口"""

    def test_depart_salary_bar(self):
        self.login(self.admin)
        dept2 = Department.objects.create(title="市场部")
        emp2 = Employee.objects.create(name="李四", age=30, gender=1, balance=0,
                                       entry_date="2026-01-01", mobile="13800000002", depart=dept2)
        Salary.objects.create(employee=self.emp, month="2026-10", base_salary=8000)
        Salary.objects.create(employee=emp2, month="2026-10", base_salary=5000)

        data = self.client.get("/chart/depart/salary/").json()
        self.assertTrue(data["status"])
        self.assertEqual(set(data["data"]["x_axis"]), {"技术部", "市场部"})
        self.assertEqual(len(data["data"]["series_list"]), 1)
        self.assertEqual(sum(data["data"]["series_list"][0]["data"]), 13000.0)

    def test_chart_page_renders(self):
        self.login(self.admin)
        self.assertEqual(self.client.get("/chart/").status_code, 200)
