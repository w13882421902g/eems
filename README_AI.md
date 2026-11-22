# AI 智能助手模块 · 配置与答辩说明

大模型统一走 OpenAI 兼容协议（`app01/utils/ai.py` 封装），项目只负责「封装调用 + 编写提示词 + 注入资料」。
换服务商只需改三个配置项，不改代码。

## 一、功能清单

| 编号 | 功能 | 路由 / 位置 | 说明 |
|---|---|---|---|
| T1 | LLMClient 统一封装 | `app01/utils/ai.py` | `chat()` 非流式、`chat_stream()` 流式；含超时、输入过滤、异常兜底 |
| T2 | 招聘 JD 生成 | `/ai/jd/` | 岗位名称 → 职责 / 任职要求 / 薪资三段式 JD |
| T3 | 制度知识库问答 | `/ai/knowledge/qa/`、`/ai/kb/` | 分词检索制度库 → 按命中权重排序 → 注入提示词，无资料答“不知道” |
| T4 | 数据智能点评 | `/ai/comment/`、`/ai/review/` | 员工月度考勤 + 薪资 → 点评与改进建议，受数据范围限制 |
| T5 | 多轮对话 | `/ai/chat/` | session 保留最近 3 轮，支持追问 |
| T6 | 安全与健壮性 | `app01/utils/security.py` | 长度限制、注入话术拦截、1 秒频率限制、越权拦截 |
| T7 | 数据问答 | `app01/utils/data_qa.py` | “有多少员工 / 本月迟到几次 / 某人薪资”等查库问题，按角色数据范围作答 |
| T8 | 全局 AI 浮窗 | `templates/app01/_ai_widget.html` | 全站右下角，SSE 流式输出，与工作台共用会话历史 |
| T9 | 离线兜底 | `app01/utils/offline_ai.py` | 未配 Key / 接口异常时按规则生成，页面不报错 |

AI 工作台入口：`/ai/` 或 `/ai/assistant/`。

## 二、配置大模型接口

### 1. 安装依赖

```powershell
cd E:\eems
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

> Django 4.2.30、PyMySQL、Pillow、openpyxl、openai、cryptography。

### 2. 填写 `.env`（推荐，持久生效）

项目根目录已生成 `.env`（该文件已被 `.gitignore` 忽略，不会进版本库）。只需改一行：

```ini
AI_API_KEY=sk-你的Key
AI_BASE_URL=https://api.siliconflow.cn/v1
AI_MODEL=Qwen/Qwen2.5-7B-Instruct
AI_TIMEOUT=20
```

`settings.py` 的读取顺序：**系统环境变量 > `.env` > 空值（走规则兜底）**。
模板见 `.env.example`。

### 3. 各服务商对应值

| 服务商 | `AI_BASE_URL` | `AI_MODEL` |
|---|---|---|
| 硅基流动 | `https://api.siliconflow.cn/v1` | `Qwen/Qwen2.5-7B-Instruct`（可换平台其它模型） |
| DeepSeek | `https://api.deepseek.com/v1` | `deepseek-chat` |
| 阿里百炼 | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `qwen-plus` |
| 火山方舟（豆包） | `https://ark.cn-beijing.volces.com/api/v3` | 推理接入点 ID（`ep-xxx`） |
| OpenAI | `https://api.openai.com/v1` | `gpt-4o-mini` |

### 4. 自检

```powershell
.venv\Scripts\python.exe manage.py check_ai          # 查看配置（Key 脱敏）
.venv\Scripts\python.exe manage.py check_ai --test   # 真实调用一次，验证 Key / 地址 / 网络
```

未配置 Key 时命令会提示，AI 页面顶部也会显示黄色提示条，功能自动走规则兜底。

### 5. 迁移与知识库

```powershell
.venv\Scripts\python.exe manage.py migrate
.venv\Scripts\python.exe manage.py init_knowledge
```

> `migrate` 已包含 AI 所需的 `Knowledge.category / keywords / updated_at` 与 `Employee.user` 字段。

## 三、启动

```powershell
.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000
```

访问 `http://127.0.0.1:8000/`，登录后进「智能助手」，或直接用右下角浮窗。

## 四、答辩演示路径

1. **招聘 JD**：输入「Java 后端工程师」→ 职责 / 要求 / 薪资三段结构。
2. **制度问答**：问「报销需要什么材料」→ 命中《报销制度》；问「今天股票涨了多少」→ 明确回答“不知道”，说明资料限定。
3. **数据问答**：超管问「公司现在有多少员工」→ 全量统计；切部门管理员问同题 → 只统计本部门；切员工问「我的工资是多少」→ 只答本人。
4. **数据点评**：选员工 + 月份 → 结合考勤与薪资生成点评；员工账号只能点评自己。
5. **多轮对话**：先问制度问题，再追问「那如果缺勤呢？」→ 展示上下文；浮窗内逐字流式输出。
6. **安全**：输入超长文本或“忽略以上指令”→ 被拦截并返回友好提示。

## 五、关键实现对照

- **三段式提示词**：`app01/utils/prompts.py`（角色 system + 任务 + 输出格式）。
- **上下文注入**：T3 注入检索到的制度条目；T4 注入结构化数据文本；T7 直接查库，不让模型编数字。
- **权限约束**：AI 数据问答与点评统一走 `app01/utils/scope.py`，与页面列表同口径。
- **失败兜底**：未配 Key、401、超时、网络异常都返回可展示文本，附 `mode=offline` 标识。
- **Key 安全**：代码无明文 Key；`.env` 不入库；`check_ai` 输出脱敏。

## 六、常见问题

- **页面提示“尚未配置大模型 Key”**：`.env` 中 `AI_API_KEY` 为空；填好后重启服务。
- **`check_ai --test` 报 401**：Key 与服务商不匹配，或 Key 已失效。
- **报 404 模型不存在**：`AI_MODEL` 名称不完整，按服务商文档复制准确标识。
- **回答“不知道”**：制度库未收录该问题，属预期行为；补充 `Knowledge` 条目或重跑 `init_knowledge`。
- **调用超时**：检查网络/代理，适当调大 `AI_TIMEOUT`。
- **不想配 Key 也能演示**：保持 `AI_API_KEY=` 为空即可，全部功能走规则兜底。
