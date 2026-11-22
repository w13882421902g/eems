"""
知识库初始化命令：预置考勤、报销、请假等制度条目
用法：python manage.py init_knowledge
"""
from django.core.management.base import BaseCommand
from app01.models import Knowledge


KNOWLEDGE_DATA = [
    (
        "考勤打卡制度", "考勤",
        "打卡,迟到,早退,缺勤,上班时间,绩效",
        "公司标准工作时间为周一至周五 9:00-18:00，中午 12:00-13:30 为午休时间。"
        "上班晚于 9:00 到岗记为迟到，下班早于 18:00 离岗记为早退；"
        "未打卡且未履行请假手续记为缺勤。每月迟到、早退累计超过 3 次，将影响当月绩效奖金。"
    ),
    (
        "报销制度", "报销",
        "报销,发票,差旅,交通费,招待费,标准",
        "因公产生的交通费、差旅费、业务招待费可申请报销。报销须在费用发生后 15 个工作日内提交，"
        "并附正规发票及消费明细；交通费按实报销，差旅费住宿标准为每人每晚不超过 300 元，"
        "业务招待费需提前经部门负责人审批。发票抬头须为公司全称，个人消费不予报销。"
    ),
    (
        "请假制度", "请假",
        "请假,年假,病假,事假,婚假,产假,审批",
        "员工请假分为事假、病假、年假、婚假、产假等。请假 1 天以内由部门负责人审批，"
        "超过 1 天须报人事部门备案。病假需提供医院证明；年假按工龄计算，入职满 1 年可享 5 天年假，"
        "满 10 年可享 10 天年假。请假应提前在系统提交申请，紧急情况可先口头报备后补办手续。"
    ),
    (
        "加班与调休制度", "考勤",
        "加班,调休,节假日,加班费,审批",
        "工作日加班一般不超过 2 小时，周末加班优先安排调休；"
        "调休须在加班后 3 个月内使用完毕。法定节假日加班按国家规定支付加班工资，"
        "加班须提前提交申请并经部门负责人批准，未经审批的自行延时不计为加班。"
    ),
    (
        "薪酬发放制度", "薪资",
        "工资,发薪,奖金,扣款,社保,个税",
        "公司每月 15 日发放上月工资，工资由基本工资、奖金、扣款构成，实发工资 = 基本工资 + 奖金 - 扣款。"
        "社保及个人所得税由公司依法代扣代缴。对工资明细有异议的，可在发薪后 5 个工作日内向人事部核对。"
    ),
]


class Command(BaseCommand):
    help = "预置企业制度知识库条目（考勤、报销、请假等）"

    def handle(self, *args, **options):
        for title, category, keywords, content in KNOWLEDGE_DATA:
            obj, created = Knowledge.objects.get_or_create(
                title=title,
                defaults={
                    "category": category,
                    "keywords": keywords,
                    "content": content,
                },
            )
            if not created:
                # 老数据补齐分类与关键词，保证 AI 检索能命中（关键词直接影响召回率）
                changed = False
                if obj.category != category:
                    obj.category = category
                    changed = True
                if not obj.keywords:
                    obj.keywords = keywords
                    changed = True
                if changed:
                    obj.save(update_fields=["category", "keywords"])
            if created:
                self.stdout.write(self.style.SUCCESS(f"知识库条目《{title}》创建成功"))
            else:
                self.stdout.write(self.style.WARNING(f"《{title}》已存在，跳过"))

        self.stdout.write(self.style.SUCCESS(f"知识库初始化完成，共 {Knowledge.objects.count()} 条"))
