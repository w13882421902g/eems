"""
通用分页组件（对应讲义第 16 章「分页」）

设计目标：
- 一次只把当前页的数据查出来（QuerySet 切片会被翻译成 SQL 的 LIMIT/OFFSET），
  避免把整张表读进内存；
- 页码链接自动带上当前地址栏的其他查询参数（keyword、depart_id 等），
  翻页后筛选条件不会丢失；
- 页码非法（0、负数、字母、超出范围）时自动回退到合法页，不抛 500。

使用方式（视图里两行）：
    page_object = Pagination(request, queryset, page_size=10)
    context = {
        "page_queryset": page_object.page_queryset,   # 当前页的数据
        "page_string": page_object.html(),            # 页码 HTML
        "total_count": page_object.total_count,       # 总条数
    }
"""
from django.core.paginator import Paginator, EmptyPage
from django.utils.safestring import mark_safe
from django.utils.html import escape


class Pagination:
    """对 Django 原生 Paginator 的薄封装，额外提供页码 HTML 生成。"""

    def __init__(self, request, queryset, page_size=10, page_param="page", plus=5):
        """
        :param request:    当前请求，用来读取页码和保留其他查询参数
        :param queryset:   已排序的 QuerySet（务必显式 order_by，否则分页顺序不稳定）
        :param page_size:  每页条数
        :param page_param: 页码参数名，默认 ?page=
        :param plus:       当前页左右各显示多少个页码
        """
        self.request = request
        self.page_param = page_param
        self.plus = plus

        # 1. 解析页码：非数字一律按第 1 页处理，避免 int("abc") 抛异常
        raw_page = request.GET.get(page_param, "1")
        page_number = int(raw_page) if str(raw_page).isdigit() else 1
        page_number = max(page_number, 1)

        # 2. 分页：queryset.count() + 切片查询，只取当前页
        paginator = Paginator(queryset, page_size)
        try:
            self.page_object = paginator.page(page_number)
        except EmptyPage:
            # 页码超出范围（例如手改地址栏 ?page=999）时回退到最后一页
            self.page_object = paginator.page(paginator.num_pages or 1)

        self.page_queryset = self.page_object.object_list
        self.total_count = paginator.count

    def _url(self, page_number):
        """构造翻页链接：保留原查询参数，只替换 page。"""
        query = self.request.GET.copy()
        query.pop(self.page_param, None)      # 先移除旧页码，避免重复参数
        query[self.page_param] = page_number
        # urlencode 会对参数值做百分号编码，因此拼接进 HTML 是安全的
        return "?" + query.urlencode()

    def _item(self, text, href=None, active=False, disabled=False):
        """生成一个 <li>：disabled/active 时不再带可点击链接。"""
        css = []
        if active:
            css.append("active")
        if disabled:
            css.append("disabled")
        css_attr = ' class="%s"' % " ".join(css) if css else ""

        if href and not (active or disabled):
            return '<li%s><a href="%s">%s</a></li>' % (css_attr, escape(href), escape(text))
        return '<li%s><a href="#">%s</a></li>' % (css_attr, escape(text))

    def html(self):
        """生成 Bootstrap 3 风格的分页条（首页/上一页/页码窗口/下一页/尾页）。"""
        page = self.page_object
        paginator = page.paginator
        num_pages = paginator.num_pages or 1
        current = page.number

        parts = [
            self._item("共 %d 条" % self.total_count, disabled=True),
            self._item("首页", self._url(1), disabled=current == 1),
            self._item("上一页", self._url(current - 1), disabled=not page.has_previous()),
        ]

        # 只渲染当前页附近的页码，避免上百页时把页面撑爆
        start = max(1, current - self.plus)
        end = min(num_pages, current + self.plus)
        if start > 1:
            parts.append(self._item("...", disabled=True))
        for number in range(start, end + 1):
            parts.append(self._item(number, self._url(number), active=number == current))
        if end < num_pages:
            parts.append(self._item("...", disabled=True))

        parts.append(self._item("下一页", self._url(current + 1), disabled=not page.has_next()))
        parts.append(self._item("尾页(%d)" % num_pages, self._url(num_pages), disabled=current == num_pages))

        return mark_safe('<ul class="pagination">%s</ul>' % "".join(parts))
