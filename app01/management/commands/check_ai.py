"""
AI 配置自检命令（不打印完整 Key）

用法：
    python manage.py check_ai           # 只看配置
    python manage.py check_ai --test    # 真实调用一次，验证 Key 与网络是否可用

输出：配置来源、脱敏后的 Key、BaseURL、模型名、超时、最近一次调用结果。
"""
import time

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from app01.utils.ai import LLMClient


def _mask(key):
    """Key 脱敏：保留前 4 位和后 4 位，中间打码；太短则只显示长度"""
    if not key:
        return "未配置"
    if len(key) < 12:
        return "已配置（长度 %d，过短，建议核对）" % len(key)
    return key[:4] + "*" * (len(key) - 8) + key[-4:]


class Command(BaseCommand):
    help = "检查大模型接口配置，可选做一次真实连通性测试"

    def add_arguments(self, parser):
        parser.add_argument(
            "--test", action="store_true",
            help="真实调用一次模型，验证 Key / BaseURL / 网络是否可用",
        )

    def handle(self, *args, **options):
        key = settings.AI_API_KEY
        self.stdout.write("AI 配置：")
        self.stdout.write("  Key      : %s" % _mask(key))
        self.stdout.write("  BaseURL  : %s" % settings.AI_BASE_URL)
        self.stdout.write("  模型     : %s" % settings.AI_MODEL)
        self.stdout.write("  超时     : %s 秒" % settings.AI_TIMEOUT)
        self.stdout.write("  配置文件 : %s" % (".env 存在时会被自动读取；系统环境变量优先"))

        if not key:
            self.stdout.write(self.style.WARNING(
                "当前未配置 AI_API_KEY：AI 功能会走规则兜底（页面不报错）。\n"
                "配置方法：打开项目根目录 .env，把 AI_API_KEY= 后面填上你的 Key，重启服务即可。\n"
                "查看模板：.env.example"
            ))
            return

        if not options["test"]:
            self.stdout.write(self.style.SUCCESS("配置已读取；如需验证连通性，请加 --test"))
            return

        started = time.time()
        result = LLMClient.chat(
            "请只回复四个字：连接成功",
            temperature=0.0,
        )
        cost = time.time() - started
        mode = getattr(result, "mode", "llm")
        if mode != "llm":
            raise CommandError(
                "调用失败（耗时 %.1fs）：%s\n"
                "排查建议：1) Key 是否正确/有额度；2) BaseURL 是否与服务商匹配；3) 网络/代理是否可达。"
                % (cost, getattr(result, "error", "") or str(result)[:200])
            )
        self.stdout.write(self.style.SUCCESS(
            "调用成功（耗时 %.1fs），模型返回：%s" % (cost, str(result).strip()[:120])
        ))
