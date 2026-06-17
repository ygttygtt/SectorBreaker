"""Structured card generator — converts LLM JSON output into Obsidian Markdown cards.

Each card follows a consistent structure:
- Frontmatter (YAML) with metadata
- Structured sections with evidence references
- Obsidian [[links]] to related cards
"""

import json
from datetime import UTC, datetime
from typing import Any


def _frontmatter(project: str, card_type: str, tags: list[str],
                 related: list[str] | None = None, evidence_ids: list[str] | None = None) -> str:
    """Generate Obsidian YAML frontmatter."""
    lines = [
        "---",
        f'project: "{project}"',
        f'type: "{card_type}"',
        f"generated_at: \"{datetime.now(UTC).strftime('%Y-%m-%d')}\"",
    ]
    if tags:
        lines.append(f"tags: [{', '.join(tags)}]")
    if related:
        lines.append(f"aliases: [{', '.join(related)}]")
    if evidence_ids:
        lines.append(f"evidence_ids: [{', '.join(evidence_ids)}]")
    lines.append("---\n")
    return "\n".join(lines)


def _evidence_footnotes(evidence_ids: list[str], evidence_map: dict[str, dict]) -> str:
    """Generate evidence footnotes section."""
    if not evidence_ids:
        return ""
    lines = ["\n---\n", "## 引用证据\n"]
    for eid in evidence_ids:
        ev = evidence_map.get(eid, {})
        source = ev.get("source_title", eid)
        snippet = ev.get("snippet", "")[:80]
        lines.append(f"- **[{eid}]** {source}: {snippet}")
    return "\n".join(lines)


def _related_links(items: list[str]) -> str:
    """Generate related links section with Obsidian [[links]]."""
    if not items:
        return ""
    links = " | ".join(f"[[{item}]]" for item in items)
    return f"\n\n**相关**：{links}\n"


# ── Industry Map Cards ────────────────────────────────────────

def generate_industry_map_cards(
    domain: str,
    data: dict[str, Any],
    project_name: str,
    evidence_ids: list[str] | None = None,
) -> dict[str, str]:
    """Generate industry map cards from structured LLM output.

    Expected data format:
    {
        "nodes": [
            {
                "name": "供给侧",
                "type": "supply",  # supply/demand/channel/risk
                "definition": "...",
                "children": [
                    {"name": "产品", "definition": "...", "questions": [...], "misconceptions": [...]}
                ],
                "questions": [...],
                "misconceptions": [...]
            }
        ],
        "learning_order": ["供给侧", "需求侧", ...],
        "misconceptions": ["误解1", ...]
    }
    """
    cards: dict[str, str] = {}
    ev = evidence_ids or []
    nodes = data.get("nodes", [])
    learning_order = data.get("learning_order", [])
    global_misconceptions = data.get("misconceptions", [])

    # 1. Generate overview card
    overview_lines = [
        _frontmatter(project_name, "industry_map_overview", ["行业地图", "总览"]),
        f"# {domain} 行业地图\n",
        "## 一级节点\n",
    ]
    for node in nodes:
        node_type = {"supply": "供给侧", "demand": "需求侧", "channel": "渠道", "risk": "风险"}.get(
            node.get("type", ""), "其他"
        )
        overview_lines.append(f"- **{node['name']}** `[{node_type}]` → [[{node['name']}]]")

    if learning_order:
        overview_lines.append("\n## 新手学习顺序\n")
        for i, name in enumerate(learning_order, 1):
            overview_lines.append(f"{i}. [[{name}]]")

    if global_misconceptions:
        overview_lines.append("\n## 新手最容易误解的地方\n")
        for m in global_misconceptions:
            overview_lines.append(f"- ❌ {m}")

    overview_lines.append(_evidence_footnotes(ev, {}))
    cards["00-总览"] = "\n".join(overview_lines)

    # 2. Generate node cards
    for node in nodes:
        node_name = node.get("name", "未知")
        node_type = node.get("type", "")
        children = node.get("children", [])
        questions = node.get("questions", [])
        misconceptions = node.get("misconceptions", [])
        definition = node.get("definition", "")

        related = [n["name"] for n in nodes if n["name"] != node_name][:3]

        card_lines = [
            _frontmatter(project_name, "industry_map_node", ["行业地图", node_name],
                         related=related, evidence_ids=ev),
            f"# {node_name}\n",
        ]

        if definition:
            card_lines.append(f"## 定义\n\n{definition}\n")

        if children:
            card_lines.append("## 子节点\n")
            for child in children:
                child_name = child.get("name", "")
                child_def = child.get("definition", "")
                card_lines.append(f"### {child_name}")
                if child_def:
                    card_lines.append(f"\n{child_def}\n")
                child_qs = child.get("questions", [])
                if child_qs:
                    card_lines.append("\n**关键问题**：")
                    for q in child_qs:
                        card_lines.append(f"- {q}")
                child_mis = child.get("misconceptions", [])
                if child_mis:
                    card_lines.append("\n**常见误区**：")
                    for m in child_mis:
                        card_lines.append(f"- ❌ {m}")
                card_lines.append("")

        if questions:
            card_lines.append("## 关键问题\n")
            for q in questions:
                card_lines.append(f"- {q}")

        if misconceptions:
            card_lines.append("\n## 常见误区\n")
            for m in misconceptions:
                card_lines.append(f"- ❌ {m}")

        card_lines.append(f"\n→ [[00-总览]]")
        card_lines.append(_evidence_footnotes(ev, {}))
        cards[node_name] = "\n".join(card_lines)

    return cards


# ── Competitor Cards ──────────────────────────────────────────

def generate_competitor_cards(
    domain: str,
    data: dict[str, Any],
    project_name: str,
    evidence_ids: list[str] | None = None,
) -> dict[str, str]:
    """Generate competitor analysis cards from structured LLM output.

    Expected data format:
    {
        "players": [
            {
                "name": "汤臣倍健",
                "role": "提供服务者",
                "positioning": "...",
                "target_users": "...",
                "products": "...",
                "pricing": "...",
                "channels": "...",
                "conversion": "...",
                "trust_assets": "...",
                "retention": "...",
                "content_strategy": "...",
                "differentiation": "...",
                "risks": "...",
                "learn": "...",
                "avoid": "..."
            }
        ]
    }
    """
    cards: dict[str, str] = {}
    ev = evidence_ids or []
    players = data.get("players", [])

    # Overview card
    overview_lines = [
        _frontmatter(project_name, "competitor_overview", ["竞品分析", "总览"]),
        f"# {domain} 竞品分析总览\n",
        "## 玩家列表\n",
        "| 玩家 | 角色 | 定位 | 主推产品 |",
        "|------|------|------|---------|",
    ]
    for p in players:
        overview_lines.append(
            f"| [[{p.get('name', '')}]] | {p.get('role', '')} | {p.get('positioning', '')[:20]} | {p.get('products', '')[:20]} |"
        )
    overview_lines.append(_evidence_footnotes(ev, {}))
    cards["00-竞品总览"] = "\n".join(overview_lines)

    # Individual player cards
    dims = [
        ("定位", "positioning"), ("目标用户", "target_users"), ("主推产品", "products"),
        ("价格结构", "pricing"), ("获客渠道", "channels"), ("转化路径", "conversion"),
        ("信任资产", "trust_assets"), ("复购机制", "retention"), ("内容策略", "content_strategy"),
        ("差异化优势", "differentiation"), ("潜在风险", "risks"),
        ("应该学习", "learn"), ("不应该照搬", "avoid"),
    ]

    for p in players:
        name = p.get("name", "未知")
        role = p.get("role", "")
        related = [pl["name"] for pl in players if pl["name"] != name][:3]

        card_lines = [
            _frontmatter(project_name, "competitor_card", ["竞品分析", name, role],
                         related=related, evidence_ids=ev),
            f"# {name}\n",
            f"**角色**：{role}\n",
        ]

        for label, key in dims:
            value = p.get(key, "")
            if value:
                card_lines.append(f"## {label}\n\n{value}\n")

        card_lines.append(f"\n→ [[00-竞品总览]]")
        card_lines.append(_evidence_footnotes(ev, {}))
        cards[name] = "\n".join(card_lines)

    return cards


# ── Transaction Unit Cards ────────────────────────────────────

def generate_transaction_unit_cards(
    domain: str,
    data: dict[str, Any],
    project_name: str,
    evidence_ids: list[str] | None = None,
) -> dict[str, str]:
    """Generate transaction unit cards from structured LLM output.

    Expected data format:
    {
        "units": [
            {
                "name": "维生素/矿物质补充剂",
                "why_buy": "...",
                "price_range": "...",
                "frequency": "...",
                "repurchase_cycle": "...",
                "decision_cost": "...",
                "delivery_difficulty": "...",
                "risks": "...",
                "margin_source": "...",
                "selling_points": "...",
                "user_keywords": "..."
            }
        ]
    }
    """
    cards: dict[str, str] = {}
    ev = evidence_ids or []
    units = data.get("units", [])

    # Overview
    overview_lines = [
        _frontmatter(project_name, "transaction_units_overview", ["交易单位", "总览"]),
        f"# {domain} 交易单位\n",
        "| 交易单位 | 客单价 | 购买频率 | 复购周期 |",
        "|---------|--------|---------|---------|",
    ]
    for u in units:
        name = u.get("name", "")
        overview_lines.append(
            f"| [[{name}]] | {u.get('price_range', '')} | {u.get('frequency', '')} | {u.get('repurchase_cycle', '')} |"
        )
    overview_lines.append(_evidence_footnotes(ev, {}))
    cards["00-交易单位总览"] = "\n".join(overview_lines)

    # Individual unit cards
    dims = [
        ("用户为什么购买", "why_buy"), ("客单价区间", "price_range"),
        ("购买频率", "frequency"), ("复购周期", "repurchase_cycle"),
        ("决策成本", "decision_cost"), ("交付难度", "delivery_difficulty"),
        ("风险点", "risks"), ("毛利来源", "margin_source"),
        ("内容卖点", "selling_points"), ("用户评价关键词", "user_keywords"),
    ]

    for u in units:
        name = u.get("name", "未知")
        related = [un["name"] for un in units if un["name"] != name][:3]

        card_lines = [
            _frontmatter(project_name, "transaction_unit", ["交易单位", name],
                         related=related, evidence_ids=ev),
            f"# {name}\n",
        ]

        for label, key in dims:
            value = u.get(key, "")
            if value:
                card_lines.append(f"## {label}\n\n{value}\n")

        card_lines.append(f"\n→ [[00-交易单位总览]]")
        card_lines.append(_evidence_footnotes(ev, {}))
        cards[name] = "\n".join(card_lines)

    return cards


# ── Opportunity Cards ─────────────────────────────────────────

def generate_opportunity_cards(
    domain: str,
    data: dict[str, Any],
    project_name: str,
    evidence_ids: list[str] | None = None,
) -> dict[str, str]:
    """Generate opportunity cards from structured LLM output.

    Expected data format:
    {
        "overall": "...",
        "hypotheses": [
            {
                "name": "功能性食品",
                "logic": "...",
                "target_users": "...",
                "underserved": "...",
                "barriers": "...",
                "resources": "...",
                "risks": "...",
                "validate_week1": "..."
            }
        ]
    }
    """
    cards: dict[str, str] = {}
    ev = evidence_ids or []
    hypotheses = data.get("hypotheses", [])
    overall = data.get("overall", "")

    # Overview
    overview_lines = [
        _frontmatter(project_name, "opportunity_overview", ["机会地图", "总览"]),
        f"# {domain} 机会地图\n",
    ]
    if overall:
        overview_lines.append(f"## 行业整体判断\n\n{overall}\n")

    overview_lines.append("## 机会假设\n")
    for h in hypotheses:
        name = h.get("name", "")
        overview_lines.append(f"- [[{name}]]：{h.get('logic', '')[:60]}")
    overview_lines.append(_evidence_footnotes(ev, {}))
    cards["00-机会总览"] = "\n".join(overview_lines)

    # Individual hypothesis cards
    dims = [
        ("机会逻辑", "logic"), ("目标用户", "target_users"),
        ("供给不足领域", "underserved"), ("进入门槛", "barriers"),
        ("需要的资源", "resources"), ("主要风险", "risks"),
        ("第一周验证", "validate_week1"),
    ]

    for h in hypotheses:
        name = h.get("name", "未知")
        related = [hy["name"] for hy in hypotheses if hy["name"] != name][:3]

        card_lines = [
            _frontmatter(project_name, "opportunity_hypothesis", ["机会假设", name],
                         related=related, evidence_ids=ev),
            f"# {name}\n",
        ]

        for label, key in dims:
            value = h.get(key, "")
            if value:
                card_lines.append(f"## {label}\n\n{value}\n")

        card_lines.append(f"\n→ [[00-机会总览]]")
        card_lines.append(_evidence_footnotes(ev, {}))
        cards[name] = "\n".join(card_lines)

    return cards


# ── Content Account Cards ─────────────────────────────────────

def generate_content_account_cards(
    domain: str,
    data: dict[str, Any],
    project_name: str,
    evidence_ids: list[str] | None = None,
) -> dict[str, str]:
    """Generate content account cards from structured LLM output.

    Expected data format:
    {
        "platforms": [
            {
                "platform": "小红书",
                "accounts": [
                    {
                        "name": "健康生活家",
                        "followers": "50-100万",
                        "direction": "...",
                        "conversion": "...",
                        "learn": "..."
                    }
                ]
            }
        ]
    }
    """
    cards: dict[str, str] = {}
    ev = evidence_ids or []
    platforms = data.get("platforms", [])

    # Overview
    overview_lines = [
        _frontmatter(project_name, "content_accounts_overview", ["内容账号", "总览"]),
        f"# {domain} 内容账号数据库\n",
    ]
    for p in platforms:
        platform = p.get("platform", "")
        overview_lines.append(f"- [[{platform}]]：{len(p.get('accounts', []))} 个账号类型")
    overview_lines.append(_evidence_footnotes(ev, {}))
    cards["00-内容账号总览"] = "\n".join(overview_lines)

    # Per-platform cards
    for p in platforms:
        platform = p.get("platform", "未知")
        accounts = p.get("accounts", [])

        card_lines = [
            _frontmatter(project_name, "content_platform", ["内容账号", platform],
                         evidence_ids=ev),
            f"# {platform} 内容账号\n",
        ]

        for acc in accounts:
            acc_name = acc.get("name", "")
            card_lines.append(f"## {acc_name}\n")
            for field in ["followers", "direction", "conversion", "learn"]:
                label = {
                    "followers": "粉丝量级", "direction": "内容方向",
                    "conversion": "转化方式", "learn": "值得学习",
                }[field]
                value = acc.get(field, "")
                if value:
                    card_lines.append(f"**{label}**：{value}\n")

        card_lines.append(f"\n→ [[00-内容账号总览]]")
        cards[platform] = "\n".join(card_lines)

    return cards


# ── Learning Path Card ────────────────────────────────────────

def generate_learning_path_card(
    domain: str,
    data: dict[str, Any],
    project_name: str,
) -> str:
    """Generate learning path card from research frame + industry map data.

    Expected data format:
    {
        "steps": [
            {"stage": "入门", "items": ["行业定义", "市场概况", ...]},
            {"stage": "深入", "items": ["玩家分析", "交易单位", ...]},
            {"stage": "实战", "items": ["机会验证", "内容策略", ...]}
        ]
    }
    """
    lines = [
        _frontmatter(project_name, "learning_path", ["学习路径"]),
        f"# {domain} 学习路径\n",
    ]

    for step in data.get("steps", []):
        stage = step.get("stage", "")
        items = step.get("items", [])
        lines.append(f"## {stage}\n")
        for item in items:
            lines.append(f"- [[{item}]]")
        lines.append("")

    return "\n".join(lines)
