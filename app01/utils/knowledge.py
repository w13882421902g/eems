"""
制度知识库检索（对应 AI 模块 T3 的“SQL 关键词检索”环节，对照参考仓库移植）

流程：问题分词 -> 用 ORM 的 icontains 在 title/keywords/content 上做 SQL 查询
      -> 按命中权重打分 -> 取最相关的若干条注入提示词
"""
import re

from django.db.models import Q

from app01.models import Knowledge

# 中文疑问词/无意义词，切词时先剔除，避免“怎么”“多少”这类词参与检索
STOP_WORDS = (
    "请问", "怎么样", "怎么", "怎样", "如何", "什么", "哪些", "哪个",
    "多少", "几天", "几个", "可以", "需要", "是否", "能不能", "有没有",
    "我们", "公司", "我想", "一下", "的话", "吗", "呢", "吧", "的", "了",
)


def extract_terms(question, max_terms=16):
    """
    把自然语言问题切成用于 SQL 检索的关键词。

    中文没有空格，直接整段当关键词会检索不到（例如“年假有几天”切成“年假有”），
    数据库里只有“年假”。所以对每一段同时保留整段和相邻二元词，扩大召回。
    """
    text = (question or "").strip()
    terms = []

    # 1) 英文、数字直接作为关键词
    terms.extend(re.findall(r"[A-Za-z0-9]{2,}", text))

    # 2) 中文先按标点切分，再剔除疑问词
    for segment in re.split(r"[^\u4e00-\u9fa5A-Za-z0-9]+", text):
        segment = segment.strip()
        if not segment:
            continue
        for word in sorted(STOP_WORDS, key=len, reverse=True):
            segment = segment.replace(word, " ")
        for piece in segment.split():
            piece = piece.strip()
            if len(piece) < 2:
                continue
            # 整段（过长只留前 4 字）作为强关键词
            terms.append(piece if len(piece) <= 8 else piece[:4])
            # 相邻二元词作为补充关键词，解决“年假有”这类切不准的情况
            if len(piece) >= 3:
                terms.extend(piece[i:i + 2] for i in range(len(piece) - 1))

    # 3) 去重且保持顺序
    unique_terms = []
    for term in terms:
        if term not in unique_terms:
            unique_terms.append(term)
    return unique_terms[:max_terms]


def search_knowledge(question, top_k=3):
    """
    检索制度知识库，返回 [{title, category, content, score}, ...]
    没有任何命中时返回空列表（上层据此回答“不知道”）
    """
    terms = extract_terms(question)
    if not terms:
        return []

    condition = Q()
    for term in terms:
        condition |= (
            Q(title__icontains=term)
            | Q(keywords__icontains=term)
            | Q(content__icontains=term)
        )
    candidates = Knowledge.objects.filter(condition)[:50]

    scored = []
    for item in candidates:
        title = item.title or ""
        keywords = item.keywords or ""
        content = item.content or ""
        score = 0
        for term in terms:
            # 标题权重最高，其次是关键词，最后是正文
            score += title.count(term) * 4
            score += keywords.count(term) * 3
            score += content.count(term) * 1
        if score > 0:
            scored.append({
                "id": item.id,
                "title": title,
                "category": item.get_category_display() if hasattr(item, "get_category_display") else "其他",
                "content": content,
                "score": score,
            })

    scored.sort(key=lambda row: row["score"], reverse=True)
    if not scored:
        return []

    # 命中分太低的条目（只偶然撞到一个字）不再当作有效依据，避免答非所问
    best = scored[0]["score"]
    cutoff = max(3, best * 0.35)
    return [row for row in scored if row["score"] >= cutoff][:top_k]


def docs_to_text(docs):
    """把检索结果拼成给提示词的资料文本"""
    if not docs:
        return ""
    blocks = []
    for index, doc in enumerate(docs, start=1):
        blocks.append(
            f"[资料{index}] 标题：{doc['title']}（分类：{doc['category']}）\n正文：{doc['content']}"
        )
    return "\n\n".join(blocks)
