# -*- coding: utf-8 -*-
"""河小智 · 首页（智能体广场式布局）。

结构：
1. ``.home-panel``：一块带边框的问候面板，内含标题、搜索与今日指标；
2. ``.home-tabs``：分类页签，全部走软导航（不刷新页面）；
3. ``.home-grid``：入口卡片墙，按页签筛选。

站内链接统一写成 ``?page=...``，由 ``core.ui.render_html`` → ``core.nav.decorate``
自动挂上软跳转标记；导航脚本失效时仍能按普通链接跳转。
"""

from __future__ import annotations

from datetime import datetime
from urllib.parse import quote

from core import auth, data, nav, policy, ui
from core.state import registrations, todo_progress


def _greeting() -> str:
    hour = datetime.now().hour
    if hour < 6:
        return "夜深了"
    if hour < 9:
        return "早上好"
    if hour < 12:
        return "上午好"
    if hour < 14:
        return "中午好"
    if hour < 18:
        return "下午好"
    return "晚上好"


def _facts(remaining: int) -> dict[str, int]:
    """卡片底部状态行里用到的真实数字。"""
    return {
        "docs": len(policy.POLICY_DOCS),
        "processes": len(data.SERVICES) + len(data.PROCESSES),
        "acts": len(data.ACTIVITIES),
        "reg": len(registrations()),
        "todos": remaining,
    }


def _metric(icon: str, value: object, unit: str, label: str, href: str) -> str:
    return f"""
<a class="metric" href="{ui.e(href)}">
  <span class="metric-icon">{ui.icon(icon, 18)}</span>
  <div class="metric-body"><div class="metric-value">{ui.e(value)}<small>{ui.e(unit)}</small></div><div class="metric-label">{ui.e(label)}</div></div>
  <span class="metric-arrow">{ui.icon('chevron-right', 16)}</span>
</a>"""


def _card(entry: dict, facts: dict) -> str:
    badge = (
        f'<span class="hc-badge">{ui.e(entry["badge"])}</span>'
        if entry.get("badge")
        else ""
    )
    foot = entry["foot"].format(**facts)
    return f"""
<a class="home-card {ui.e(entry['tone'])}" href="{ui.e(entry['href'])}">
  <span class="hc-ico">{ui.icon(entry['icon'], 18)}</span>
  <span class="hc-body">
    <h3>{ui.e(entry['title'])}{badge}</h3>
    <p>{ui.e(entry['desc'])}</p>
    <span class="hc-foot">{ui.icon(entry.get('foot_icon') or 'info', 11)}{ui.e(foot)}</span>
  </span>
  <span class="hc-go">{ui.icon('arrow-right', 15)}</span>
</a>"""


def _tabs(active: str, count: int) -> str:
    """分类页签：每个页签都是一个软链接（不整页刷新）。"""
    items = []
    for name in data.HOME_CATEGORIES:
        selected = name == active
        if name == "全部":
            params = {"page": "home"}
            href = "?page=home"
        else:
            params = {"page": "home", "cat": name}
            href = f"?page=home&cat={quote(name)}"
        items.append(
            nav.link(
                ui.e(name),
                params=params,
                href=href,
                cls="home-tab on" if selected else "home-tab",
                dedupe=f"home-cat:{name}",
            )
        )
    joined = "".join(items)
    return (
        f'<div class="home-tabs">{joined}'
        f'<span class="home-tab-count">共 {count} 个入口</span></div>'
    )


def render() -> None:
    done_count, total_count = todo_progress()
    remaining = total_count - done_count
    account = auth.current_user()
    display_name = account["username"] if account else data.USER["nickname"]

    active = ui.qp("cat").strip() or "全部"
    if active not in data.HOME_CATEGORIES:
        active = "全部"

    facts = _facts(remaining)
    entries = [
        entry
        for entry in data.HOME_ENTRIES
        if active == "全部" or entry["cat"] == active
    ]

    metrics = "".join(
        [
            _metric(
                "book-open",
                "4",
                "节",
                "今日课程 · 下一节 10:10",
                "?page=center&focus=course",
            ),
            _metric(
                "circle-check",
                remaining,
                "项",
                f"待办事项 · 已完成 {done_count}/{total_count}",
                "?page=center&focus=todo",
            ),
            _metric(
                "calendar",
                len(data.ACTIVITIES),
                "场",
                "本周活动 · 2 场即将截止",
                "?page=activities",
            ),
            _metric(
                "library",
                data.LIBRARY["borrowed"],
                "本",
                f"图书借阅 · {data.LIBRARY['due_soon']} 本 {data.LIBRARY['due_date']} 到期",
                "?page=services&q=图书馆",
            ),
        ]
    )

    ui.render_html(
        f"""
<!-- ================= 问候面板 ================= -->
<section class="home-panel">
  <div class="home-kicker"><i></i>AI CAMPUS · 一站式校园智能体</div>
  <h1 class="home-title">{_greeting()}，{ui.e(display_name)}。<br>今天想让<em>河小智</em>帮你做点什么？</h1>
  <p class="home-desc">政策、办事、活动、课表都在这里。提一句需求，AI 帮你把流程、材料与地点一次说清。</p>
  <form class="home-search" method="get" action="" role="search">
    <input type="hidden" name="page" value="qa"/>
    {ui.icon('search', 17)}
    <input name="q" type="search" placeholder="试试问我：学生证丢了怎么办？/ 这周有哪些活动可以报名？" autocomplete="off" aria-label="向河小智提问" required/>
    <button type="submit">{ui.icon('send', 14)}<span>问问河小智</span></button>
  </form>
  <div class="home-metrics">{metrics}</div>
</section>
"""
    )

    cards = "".join(_card(entry, facts) for entry in entries)
    if not cards:
        cards = '<div class="home-empty">这个分类下暂时没有入口，换个页签看看。</div>'

    ui.render_html(
        f"""
<!-- ================= 分类页签 + 入口卡片 ================= -->
{_tabs(active, len(entries))}
<div class="home-grid">{cards}</div>
"""
    )
