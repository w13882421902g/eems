"""
数据模型定义（后端数据层）

本文件是整个系统唯一的“数据结构定义”，Django 依据这里的字段自动生成建表语句，
视图层、表单层和模板层都围绕这些模型工作。

表命名约定：
- sys_*  系统与权限相关表（用户、角色、权限）
- biz_*  业务数据表（部门、员工、考勤、薪资、公告、任务）
"""
from django.db import models
from django.contrib.auth.models import AbstractUser


class User(AbstractUser):
    """
    自定义用户模型。

    直接继承 AbstractUser，而不是另建一张账号表，原因有三：
    1. 复用 Django 内置的用户名字段、邮箱、is_active（启用状态）、is_superuser（超级管理员标记）；
    2. 复用 set_password / check_password 的 PBKDF2 加盐哈希，数据库里永远不存明文密码；
    3. 通过 settings 的 AUTH_USER_MODEL = "app01.User" 把认证体系整体切到本表。

    在权限设计上，本模型同时保留两套标记：
    - is_superuser：Django 原生超级管理员，用于“用户管理/角色管理”这类系统级功能；
    - roles：业务角色（超级管理员/部门管理员/普通员工），用于功能权限分配。
    """
    # 多对多：一个用户可以拥有多个角色，一个角色也能分配给多个用户（RBAC 的基础）
    roles = models.ManyToManyField("Role", verbose_name="角色", blank=True)

    class Meta:
        db_table = "sys_user"          # 显式指定表名，方便答辩时对照数据库讲解
        verbose_name = "用户"
        verbose_name_plural = verbose_name

    def __str__(self):
        # 后台、调试和模板里输出对象时的可读名称
        return self.username


class Permission(models.Model):
    """
    权限模型：一条记录对应一个功能入口（例如“员工管理” -> /employee/list/）。

    url 字段保存的是功能入口路径，后续可扩展为“按 URL 前缀做访问控制”的权限表；
    当前版本主要通过角色勾选权限来体现“角色-权限”的分配关系。
    """
    title = models.CharField(verbose_name="权限名称", max_length=32)
    url = models.CharField(verbose_name="权限URL", max_length=128)

    class Meta:
        db_table = "sys_permission"
        verbose_name = "权限"
        verbose_name_plural = verbose_name

    def __str__(self):
        return self.title


class Role(models.Model):
    """
    角色模型：系统采用 RBAC（基于角色的访问控制）思路。

    关系链：用户 --(多对多)--> 角色 --(多对多)--> 权限。
    这样新增一个部门管理员时，只要挂到“部门管理员”角色上，不必逐个功能去授权。
    """
    title = models.CharField(verbose_name="角色名称", max_length=32)
    permissions = models.ManyToManyField("Permission", verbose_name="权限", blank=True)

    class Meta:
        db_table = "sys_role"
        verbose_name = "角色"
        verbose_name_plural = verbose_name

    def __str__(self):
        return self.title


class Department(models.Model):
    """
    部门模型。

    leader 用外键指向 User，并设置：
    - on_delete=SET_NULL：负责人离职删除账号时，部门本身保留，只把负责人置空；
    - null=True / blank=True：允许新部门暂时没有负责人；
    - related_name="lead_departments"：反向查询 user.lead_departments 可拿到他负责的部门。
    """
    title = models.CharField(verbose_name="部门名称", max_length=32)
    leader = models.ForeignKey(
        "User", verbose_name="负责人",
        on_delete=models.SET_NULL, null=True, blank=True,
        related_name="lead_departments"
    )

    class Meta:
        db_table = "biz_department"
        verbose_name = "部门"
        verbose_name_plural = verbose_name

    def __str__(self):
        return self.title


class Employee(models.Model):
    """
    员工模型（业务核心表）。

    字段设计要点：
    - mobile 唯一：手机号是天然的业务唯一键，避免重复建档；
    - balance 用 DecimalField 而不是 Float：金额必须精确到分，避免浮点误差；
    - avatar 用 ImageField + upload_to：头像文件落到 MEDIA_ROOT/avatar/ 下，数据库只存相对路径；
    - depart 外键 CASCADE：部门删除时其下员工一并删除（业务上部门被撤销则人员归属失效）。
    """
    GENDER_CHOICES = (
        (1, "男"),
        (2, "女"),
    )
    # 关联登录账号：员工登录后只能看到“自己”的数据，靠这个字段定位（对照参考仓库补充）
    user = models.OneToOneField(
        "User", verbose_name="登录账号",
        on_delete=models.SET_NULL, null=True, blank=True,
        related_name="employee"
    )
    name = models.CharField(verbose_name="姓名", max_length=16)
    age = models.IntegerField(verbose_name="年龄")
    gender = models.SmallIntegerField(verbose_name="性别", choices=GENDER_CHOICES, default=1)
    balance = models.DecimalField(verbose_name="账户余额", max_digits=10, decimal_places=2, default=0)
    entry_date = models.DateField(verbose_name="入职时间")
    mobile = models.CharField(verbose_name="手机号", max_length=11, unique=True)
    depart = models.ForeignKey("Department", verbose_name="所属部门", on_delete=models.CASCADE)
    avatar = models.ImageField(verbose_name="头像", upload_to="avatar/", null=True, blank=True)

    class Meta:
        db_table = "biz_employee"
        verbose_name = "员工"
        verbose_name_plural = verbose_name

    def __str__(self):
        return self.name


class Attendance(models.Model):
    """
    考勤模型。

    状态不是手工录入的，而是由视图层根据上下班时间自动计算后写入
    （见 views/attendance.py 的 calc_status），保证同一套规则全局一致。
    """
    STATUS_CHOICES = (
        (1, "按时"),
        (2, "迟到"),
        (3, "早退"),
        (4, "缺勤"),
    )
    employee = models.ForeignKey("Employee", verbose_name="员工", on_delete=models.CASCADE)
    date = models.DateField(verbose_name="日期")
    check_in = models.TimeField(verbose_name="上班时间", null=True, blank=True)
    check_out = models.TimeField(verbose_name="下班时间", null=True, blank=True)
    status = models.SmallIntegerField(verbose_name="考勤状态", choices=STATUS_CHOICES, default=4)

    class Meta:
        db_table = "biz_attendance"
        verbose_name = "考勤"
        verbose_name_plural = verbose_name
        # 联合唯一约束：同一员工同一天只能有一条考勤记录，从数据库层面杜绝重复录入
        unique_together = [("employee", "date")]

    def __str__(self):
        return f"{self.employee.name}-{self.date}"


class Salary(models.Model):
    """
    薪资模型。

    实发工资 total 不信任前端传值，而是在模型 save() 里统一计算：
    无论从新增、编辑还是脚本导入，口径都保持一致，避免出现“页面显示和库内不一致”。
    """
    employee = models.ForeignKey("Employee", verbose_name="员工", on_delete=models.CASCADE)
    month = models.CharField(verbose_name="月份", max_length=7)  # 格式固定为 2026-11
    base_salary = models.DecimalField(verbose_name="基本工资", max_digits=10, decimal_places=2)
    bonus = models.DecimalField(verbose_name="奖金", max_digits=10, decimal_places=2, default=0)
    deduction = models.DecimalField(verbose_name="扣款", max_digits=10, decimal_places=2, default=0)
    total = models.DecimalField(verbose_name="实发工资", max_digits=10, decimal_places=2, default=0)

    def save(self, *args, **kwargs):
        """保存前统一计算实发工资：基本工资 + 奖金 - 扣款。"""
        self.total = (self.base_salary or 0) + (self.bonus or 0) - (self.deduction or 0)
        super().save(*args, **kwargs)

    class Meta:
        db_table = "biz_salary"
        verbose_name = "薪资"
        verbose_name_plural = verbose_name
        # 同一员工同一个月只能有一条薪资记录，防止重复发放
        unique_together = [("employee", "month")]

    def __str__(self):
        return f"{self.employee.name}-{self.month}"


class Notice(models.Model):
    """
    公告模型。

    publish_time 用 auto_now_add：新增时自动写入当前时间，避免由前端伪造发布时间；
    ordering 让列表默认“置顶优先、其次按发布时间倒序”，模板层不用再手工排序。
    """
    title = models.CharField(verbose_name="标题", max_length=64)
    content = models.TextField(verbose_name="内容")
    publisher = models.ForeignKey("User", verbose_name="发布人", on_delete=models.CASCADE)
    publish_time = models.DateTimeField(verbose_name="发布时间", auto_now_add=True)
    is_top = models.BooleanField(verbose_name="是否置顶", default=False)

    class Meta:
        db_table = "biz_notice"
        verbose_name = "公告"
        verbose_name_plural = verbose_name
        ordering = ["-is_top", "-publish_time"]   # 先按置顶倒序，再按时间倒序

    def __str__(self):
        return self.title


class Task(models.Model):
    """
    任务模型（配合 AJAX 新建任务使用）。

    level 用 1/2/3 存“紧急/普通/不急”，展示时用 get_level_display() 转成中文，
    这样数据库存的是稳定枚举值，界面文案可以随时调整而不影响数据。
    """
    LEVEL_CHOICES = (
        (1, "紧急"),
        (2, "普通"),
        (3, "不急"),
    )
    level = models.SmallIntegerField(verbose_name="级别", choices=LEVEL_CHOICES, default=2)
    title = models.CharField(verbose_name="标题", max_length=64)
    detail = models.TextField(verbose_name="详情", blank=True)
    leader = models.ForeignKey("User", verbose_name="负责人", on_delete=models.CASCADE)

    class Meta:
        db_table = "biz_task"
        verbose_name = "任务"
        verbose_name_plural = verbose_name

    def __str__(self):
        return self.title


class Order(models.Model):
    """
    订单模型（对应讲义第 18 章「订单管理」）。

    字段设计要点：
    - oid 存业务订单号，由后端按“时间戳 + 4 位随机数”生成并加唯一约束，
      既保证不重复，又不让前端有机会伪造；
    - status 用 1/2 存“待支付/已支付”，展示时用 get_status_display() 转中文；
    - admin 记录创建该订单的管理员，删除账号时订单一并删除（CASCADE）。
    """
    STATUS_CHOICES = (
        (1, "待支付"),
        (2, "已支付"),
    )
    oid = models.CharField(verbose_name="订单号", max_length=32, unique=True)
    title = models.CharField(verbose_name="名称", max_length=32)
    price = models.IntegerField(verbose_name="价格")
    status = models.SmallIntegerField(verbose_name="状态", choices=STATUS_CHOICES, default=1)
    admin = models.ForeignKey("User", verbose_name="管理员", on_delete=models.CASCADE)

    class Meta:
        db_table = "biz_order"
        verbose_name = "订单"
        verbose_name_plural = verbose_name
        ordering = ["-id"]      # 默认按新订单在前，列表页不必再手工排序

    def __str__(self):
        return f"{self.oid}-{self.title}"


class Knowledge(models.Model):
    """
    企业知识库（制度/手册条目），供 AI 制度问答检索。

    不引入向量数据库：问答时先用 SQL 关键词在标题、关键词、正文里模糊匹配命中条目，
    再按命中权重打分排序，把最相关的条目拼进提示词作为上下文（简化版 RAG）。

    分类 / 关键词 / 更新时间三个字段对照参考仓库补齐：
    - category：制度分类，回答时可以告诉用户“依据哪一类制度”；
    - keywords：人工维护的检索词，提高“年假 / 调休”这类同义词的召回率；
    - updated_at：自动记录最近修改时间，便于后台识别过期制度。
    """
    CATEGORY_CHOICES = (
        ("考勤", "考勤"),
        ("请假", "请假"),
        ("报销", "报销"),
        ("薪资", "薪资"),
        ("晋升", "晋升"),
        ("培训", "培训"),
        ("奖惩", "奖惩"),
        ("离职", "离职"),
        ("其他", "其他"),
    )
    title = models.CharField(verbose_name="标题", max_length=128)
    category = models.CharField(
        verbose_name="分类", max_length=16, choices=CATEGORY_CHOICES, default="其他"
    )
    keywords = models.CharField(
        verbose_name="关键词", max_length=128, blank=True,
        help_text="用逗号分隔，便于 SQL 关键词检索"
    )
    content = models.TextField(verbose_name="内容")
    updated_at = models.DateTimeField(verbose_name="更新时间", auto_now=True)

    class Meta:
        db_table = "biz_knowledge"
        verbose_name = "知识库"
        verbose_name_plural = verbose_name
        ordering = ["category", "id"]

    def __str__(self):
        return self.title
