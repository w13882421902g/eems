"""
表单样式混入类（对应讲义第 22.2 节「表单排除字段」）

作用：给 ModelForm / Form 的所有字段统一加上 Bootstrap 3 的 form-control 样式，
省去在模板里手写 class，也避免逐个字段维护。

两个关键点：
1. 用 Mixin（混入）而不是改 Django 的基类：BootStrap 只负责“遍历字段、补样式”，
   具体是普通 Form 还是 ModelForm，由 BootStrapForm / BootStrapModelForm 决定；
2. bootstrap_exclude_fields：文件上传框、复选框、单选组不能套 form-control，
   通过类属性声明排除，子类按需覆盖即可。
"""
from django import forms


# 不该套 form-control 的控件类型：套上后会变形或无法正常使用
_EXCLUDE_WIDGETS = (
    forms.CheckboxInput,
    forms.CheckboxSelectMultiple,
    forms.RadioSelect,
    forms.FileInput,
    forms.ClearableFileInput,
    forms.HiddenInput,
)


class BootStrap:
    """遍历所有字段，统一补 form-control 样式与占位提示。"""

    bootstrap_exclude_fields = []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            # 1) 显式排除的字段直接跳过
            if name in self.bootstrap_exclude_fields:
                continue
            # 2) 复选框/文件框等控件自动跳过，不需要每个子类都声明
            if isinstance(field.widget, _EXCLUDE_WIDGETS):
                continue

            attrs = field.widget.attrs or {}
            # 保留控件原有的 class（例如 date 控件），再补上 form-control
            class_names = attrs.get("class", "")
            if "form-control" not in class_names.split():
                attrs["class"] = ("form-control " + class_names).strip()
            # 没有占位提示时，用字段名兼作提示（label 为空就不加）
            if not attrs.get("placeholder") and field.label:
                attrs["placeholder"] = field.label
            field.widget.attrs = attrs


class BootStrapForm(BootStrap, forms.Form):
    """普通 Form 版本"""


class BootStrapModelForm(BootStrap, forms.ModelForm):
    """ModelForm 版本"""
