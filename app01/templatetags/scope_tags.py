"""
自定义模板过滤器（对照参考仓库 app01/templatetags/scope_tags.py 移植）

把权限判断结果直接暴露给模板用，例如：
    {% load scope_tags %}
    {% if request.current_user|is_super_admin %}...{% endif %}
"""
from django import template

from app01.utils.scope import is_super_admin as _is_super_admin

register = template.Library()


@register.filter(name="is_super_admin")
def is_super_admin(user):
    """判断用户是否超级管理员（is_superuser 或拥有超级管理员角色）"""
    return _is_super_admin(user)
