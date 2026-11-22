"""
表单校验层（后端第一道数据过滤）

设计思路：
- 页面提交的原始数据不直接写库，先经过 ModelForm 的类型转换 + 字段校验；
- 通用校验（必填、长度、外键是否存在、唯一约束）由 Django 自动完成；
- 业务规则（姓名长度、年龄区间、手机号格式与唯一性）用 clean_xxx 方法补充；
- 校验失败时表单对象会带回 fields.errors，模板可直接回显错误信息。
"""
import re
from django import forms
from app01.models import Employee, Task, Attendance, Salary, Notice, User, Role, Order
from app01.utils.bootstrap import BootStrapModelForm

# 头像上传限制：2MB 以内、常见图片格式（前端提示 + 后端强校验，不能只靠前端）
MAX_AVATAR_SIZE = 2 * 1024 * 1024
ALLOWED_AVATAR_EXT = (".jpg", ".jpeg", ".png", ".webp", ".gif")


class EmployeeModelForm(BootStrapModelForm):
    """员工表单（含姓名/年龄/手机号/头像校验）"""

    # 文件框不能套 form-control 样式，否则按钮会被拉变形
    bootstrap_exclude_fields = ["avatar"]

    class Meta:
        model = Employee
        fields = ["name", "age", "gender", "balance", "entry_date",
                  "mobile", "depart", "user", "avatar"]
        widgets = {
            # 把日期字段渲染成浏览器原生日期选择器，避免手工输入格式错误
            "entry_date": forms.DateInput(attrs={"type": "date"}),
        }

    def clean_name(self):
        """姓名至少 2 个字符，避免录入单个字或空串。"""
        name = self.cleaned_data["name"]
        if len(name) < 2:
            raise forms.ValidationError("姓名至少2个字符")
        return name

    def clean_age(self):
        """年龄限制在 18-65 岁，过滤明显不合理的输入。"""
        age = self.cleaned_data["age"]
        if not (18 <= age <= 65):
            raise forms.ValidationError("年龄必须在18-65岁之间")
        return age

    def clean_mobile(self):
        """
        手机号校验：先做正则格式校验，再做业务唯一性校验。

        注意：编辑已有员工时，唯一性检查要排除“自己”，
        否则用户只改姓名不改手机号也会被判定为重复。
        """
        mobile = self.cleaned_data["mobile"]
        if not re.match(r"^1[3-9]\d{9}$", mobile):
            raise forms.ValidationError("手机号格式错误")
        queryset = Employee.objects.filter(mobile=mobile)
        if self.instance.pk:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise forms.ValidationError("手机号已存在")
        return mobile

    def clean_user(self):
        """
        登录账号校验：一个账号只能绑定一份员工档案。

        OneToOneField 在数据库层也有唯一约束，这里提前校验是为了给出中文提示，
        避免用户看到“该字段必须唯一”这类晦涩的数据库报错。
        """
        account = self.cleaned_data.get("user")
        if account:
            queryset = Employee.objects.filter(user=account)
            if self.instance.pk:
                queryset = queryset.exclude(pk=self.instance.pk)
            if queryset.exists():
                raise forms.ValidationError("该登录账号已绑定其他员工档案")
        return account

    def clean_avatar(self):
        """
        头像校验：大小 + 格式。

        文件是否真的是图片由 ImageField 交给 Pillow 验证（伪造后缀会被识别），
        这里只补充大小和扩展名的限制，避免把超大文件写进磁盘。
        """
        avatar = self.cleaned_data.get("avatar")
        # 编辑时没有重新选择文件，clean 拿到的是原有的 FieldFile，直接放行
        if not avatar or not getattr(avatar, "name", ""):
            return avatar

        if avatar.size > MAX_AVATAR_SIZE:
            raise forms.ValidationError("头像不能超过 2MB")
        if not avatar.name.lower().endswith(ALLOWED_AVATAR_EXT):
            raise forms.ValidationError("头像仅支持 jpg / jpeg / png / webp / gif")
        return avatar


class AttendanceModelForm(BootStrapModelForm):
    """考勤表单：只让用户填员工、日期和上下班时间，状态由后端计算。"""

    class Meta:
        model = Attendance
        fields = ["employee", "date", "check_in", "check_out"]
        widgets = {
            # 使用原生 date / time 控件，减少手工输入格式错误
            "date": forms.DateInput(attrs={"type": "date"}),
            "check_in": forms.TimeInput(attrs={"type": "time"}),
            "check_out": forms.TimeInput(attrs={"type": "time"}),
        }


class SalaryModelForm(BootStrapModelForm):
    """薪资表单：实发工资不由用户填写，保存时由模型 save() 统一计算。"""

    class Meta:
        model = Salary
        fields = ["employee", "month", "base_salary", "bonus", "deduction"]


class NoticeModelForm(BootStrapModelForm):
    """公告表单：发布人、发布时间由后端写入，用户只填标题、内容和是否置顶。"""

    class Meta:
        model = Notice
        fields = ["title", "content", "is_top"]
        widgets = {
            "content": forms.Textarea(attrs={"rows": 5}),
        }


class TaskModelForm(BootStrapModelForm):
    """任务表单（AJAX 提交用），校验结果通过 JSON 返回给前端。"""

    class Meta:
        model = Task
        fields = ["level", "title", "detail", "leader"]
        widgets = {
            "detail": forms.Textarea(attrs={"rows": 4}),
        }

    def clean_title(self):
        """任务标题至少 2 个字符。"""
        title = self.cleaned_data["title"]
        if len(title) < 2:
            raise forms.ValidationError("标题至少2个字符")
        return title


class UserModelForm(BootStrapModelForm):
    """
    用户表单（不含密码）。

    密码由视图层统一设为默认密码并用 set_password 哈希，
    不放进表单，避免明文密码经过请求参数和日志。
    """

    class Meta:
        model = User
        fields = ["username", "email", "is_superuser", "is_active", "roles"]


class RoleModelForm(BootStrapModelForm):
    """角色表单：权限用复选框勾选，比原生多选列表更直观。"""

    class Meta:
        model = Role
        fields = ["title", "permissions"]
        widgets = {
            # CheckboxSelectMultiple：权限逐项打勾，避免“按住 Ctrl 多选”的操作门槛
            "permissions": forms.CheckboxSelectMultiple()
        }


class OrderModelForm(BootStrapModelForm):
    """
    订单表单（对应讲义第 18 章）。

    exclude 的作用：订单号由后端生成、管理员取当前登录人，
    这两个字段不能让前端提交，否则用户可以伪造别人的订单。
    """

    class Meta:
        model = Order
        exclude = ["oid", "admin"]

    def clean_price(self):
        """价格必须是正整数，避免 0 元或负数订单。"""
        price = self.cleaned_data.get("price")
        if price is None or price <= 0:
            raise forms.ValidationError("价格必须大于 0")
        return price
