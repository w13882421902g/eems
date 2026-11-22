"""
大模型（LLM）统一封装

任务书要求：把大模型视作“一个会写字的接口”——给它文字指令，返回文字结果。
本模块对外只暴露 LLMClient，所有视图都复用这里，便于后续统一加限流、计数、降级。

设计要点：
- 配置（Key / BaseURL / 模型名 / 超时）全部来自 settings，而 settings 又从环境变量读取；
- 客户端懒加载：同一进程只初始化一次 OpenAI 兼容客户端；
- chat() 做输入长度过滤、超时控制、异常兜底，调用方拿到的始终是“可直接展示的文本”；
- 对照参考仓库补充：未配置 Key / 接口异常时走 fallback（规则兜底），返回结果带 mode 元信息；
- 支持 chat_stream() 逐段输出，供 AI 浮窗的 SSE 流式接口使用；
- 接口兼容 OpenAI 协议，DeepSeek / 通义千问 / 智谱 GLM / 硅基流动 均可，只需改环境变量。
"""
import time

from openai import OpenAI
from django.conf import settings


# 输入/输出长度限制（T6 安全与健壮性），防止超长文本把上下文撑爆或拖慢响应
MAX_INPUT_LEN = 1000
MAX_OUTPUT_LEN = 2000


class LLMError(Exception):
    """大模型调用异常的统一类型，视图层可据此返回友好提示。"""


class AIResult(str):
    """
    既是字符串（满足 chat(prompt) -> str 的约定），又带调用元信息：

    - mode：llm（走真实大模型） / offline（规则兜底）
    - error：失败原因（成功时为空字符串）
    - model：实际使用的模型名

    这样前端既能直接显示文本，也能标注“这条回答来自模型还是规则”。
    """

    def __new__(cls, text, mode="llm", error="", model=""):
        obj = str.__new__(cls, text)
        obj.mode = mode
        obj.error = error
        obj.model = model
        return obj


class LLMClient:
    """把大模型封装成“会写字的函数”：chat(提示词) -> 文本。"""

    _client = None

    # ------------------------------------------------------------------ #
    # 基础能力
    # ------------------------------------------------------------------ #
    @classmethod
    def _get_client(cls):
        """懒加载：同一进程只初始化一次客户端。"""
        if cls._client is None:
            if not settings.AI_API_KEY:
                # Key 未配置时直接抛出明确错误，便于答辩/排障定位
                raise LLMError("尚未配置大模型 API_KEY（请先在环境变量中设置 AI_API_KEY）")
            cls._client = OpenAI(
                api_key=settings.AI_API_KEY,
                base_url=settings.AI_BASE_URL,   # 换服务只需改 base_url
                timeout=settings.AI_TIMEOUT,       # 超时兜底，避免无限等待
            )
        return cls._client

    @property
    def configured(self):
        """是否配置了 API Key（未配置时走规则兜底，演示也能跑通）"""
        return bool(settings.AI_API_KEY)

    @property
    def model(self):
        """当前使用的模型名，供页面展示"""
        return settings.AI_MODEL

    @staticmethod
    def _normalize(prompt):
        """输入清洗：去空白、截断超长内容，返回清洗后的文本；空内容抛 LLMError。"""
        if prompt is None:
            raise LLMError("输入内容不能为空")
        text = str(prompt).strip()
        if not text:
            raise LLMError("输入内容不能为空")
        if len(text) > MAX_INPUT_LEN:
            text = text[:MAX_INPUT_LEN]
        return text

    @staticmethod
    def _messages(prompt, system=None, history=None):
        """拼装 OpenAI 协议的消息数组：system + 历史 + 本轮问题。"""
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        for item in (history or []):
            # 历史对话只保留 role / content 两个字段，避免脏数据传给模型
            if isinstance(item, dict) and item.get("content"):
                role = item.get("role") if item.get("role") in ("user", "assistant") else "user"
                messages.append({"role": role, "content": str(item["content"])})
        messages.append({"role": "user", "content": prompt})
        return messages

    # ------------------------------------------------------------------ #
    # 非流式调用
    # ------------------------------------------------------------------ #
    @classmethod
    def chat(cls, prompt, system=None, temperature=0.7, history=None, fallback=None):
        """
        发送提示词，返回模型生成的文字。

        :param prompt: 用户问题/任务（必需）
        :param system: 系统角色设定（可选），用于给模型定“人设”
        :param temperature: 随机度，越低越稳定、越高越多样
        :param history: 多轮历史消息，格式 [{"role": "user"/"assistant", "content": "..."}]
        :param fallback: 未配置 Key 或调用失败时的规则兜底文本
        :return: AIResult（str 子类，可带 mode / error / model）
        """
        # 1) 没配 Key：直接用规则兜底，保证页面不报错
        if not cls.configured:
            text = fallback or "抱歉，我暂时无法生成回答，请稍后再试。"
            return AIResult(text, mode="offline", error="no_api_key", model=settings.AI_MODEL)

        try:
            prompt = cls._normalize(prompt)
            client = cls._get_client()
            resp = client.chat.completions.create(
                model=settings.AI_MODEL,
                messages=cls._messages(prompt, system=system, history=history),
                temperature=temperature,
            )
            text = (resp.choices[0].message.content or "").strip()
            if len(text) > MAX_OUTPUT_LEN:
                text = text[:MAX_OUTPUT_LEN]
            return AIResult(text, mode="llm", model=settings.AI_MODEL)
        except LLMError as error:
            text = fallback or str(error)
            return AIResult(text, mode="offline", error=str(error), model=settings.AI_MODEL)
        except Exception as error:      # 网络抖动 / 401 / 模型不存在 统一兜底
            text = fallback or f"【提示】大模型调用失败：{error}"
            return AIResult(text, mode="offline", error=str(error), model=settings.AI_MODEL)

    # ------------------------------------------------------------------ #
    # 流式调用（对照参考仓库 T7 补充）
    # ------------------------------------------------------------------ #
    @classmethod
    def chat_stream(cls, prompt, system=None, temperature=0.3, history=None, fallback=None):
        """
        逐段 yield 文本，供 SSE 流式接口使用。

        没配 Key / 调用失败时，同样对兜底文案做“逐字输出”，前端体验一致。
        """
        # 1) 没配 Key：把兜底文案切块吐出去
        if not cls.configured:
            text = fallback or "抱歉，我暂时无法生成回答，请稍后再试。"
            for piece in _split_for_typing(text):
                time.sleep(0.02)
                yield piece
            return

        try:
            prompt = cls._normalize(prompt)
            client = cls._get_client()
            stream = client.chat.completions.create(
                model=settings.AI_MODEL,
                messages=cls._messages(prompt, system=system, history=history),
                temperature=temperature,
                stream=True,
            )
            for chunk in stream:
                delta = ""
                if chunk.choices:
                    delta = chunk.choices[0].delta.content or ""
                if delta:
                    yield delta
        except Exception as error:
            text = fallback or f"【提示】大模型调用失败：{error}"
            for piece in _split_for_typing(text):
                time.sleep(0.02)
                yield piece


def _split_for_typing(text, size=8):
    """把文本切成小块，用于本地演示模式模拟逐字输出"""
    return [text[i:i + size] for i in range(0, len(text), size)]
