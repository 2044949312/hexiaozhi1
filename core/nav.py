# -*- coding: utf-8 -*-
"""河小智 · 站内软导航（soft navigation）。

Streamlit 默认的 `<a href="?page=...">` 会让浏览器整页重新加载：白屏闪一下、
滚动位置丢失、刚输入的草稿清空。本模块把站内链接改成「软跳转」：

1. 渲染时给站内链接打上 ``data-hn="<槽位>"`` 标记，并在页面底部（不可见的）
   容器里渲染同槽位的 Streamlit 按钮；
2. 页面里的 JS（同源 iframe）拦截链接点击，改为点击对应的隐藏按钮；
3. 按钮回调在服务端改 ``st.query_params`` / ``st.session_state``，Streamlit
   通过 WebSocket 重跑脚本 —— 浏览器不发生文档级 reload，URL 也会同步更新。

退化策略：JS 没生效、或槽位按钮找不到时，链接仍然保留原来的 ``href``，
点击照旧可用（等价于旧版整页跳转），功能不会丢。
"""

from __future__ import annotations

import html
import re
import streamlit as st
import streamlit.components.v1 as components
from urllib.parse import parse_qsl, urlsplit

_MAX_SLOTS = 160

_SLOTS: list[dict] = []
_INDEX: dict[tuple, int] = {}
_FLUSHED = False

# 绑定在父文档上的点击拦截脚本：不需要任何 Streamlit API，
# 只做「把点击转成隐藏按钮点击」，因此 iframe 重载与否都不影响可用性。
_BRIDGE_JS = """
<script>
(function () {
  var host = window.parent;
  var doc = null;
  try { doc = host.document; } catch (err) { return; }
  if (!doc) { return; }
  if (host.__hnClickHandler) {
    try { doc.removeEventListener('click', host.__hnClickHandler, true); } catch (err) {}
  }
  host.__hnClickHandler = function (ev) {
    if (ev.defaultPrevented) { return; }
    if (ev.button && ev.button !== 0) { return; }
    if (ev.metaKey || ev.ctrlKey || ev.shiftKey || ev.altKey) { return; }
    var el = ev.target;
    while (el && el !== doc && !(el.getAttribute && el.getAttribute('data-hn'))) {
      el = el.parentElement;
    }
    if (!el || el === doc) { return; }
    var slot = el.getAttribute('data-hn');
    var btn = doc.querySelector('.st-key-hn-' + slot + ' button');
    if (!btn) { return; }          /* 找不到桥接按钮：交给浏览器原生跳转 */
    ev.preventDefault();
    ev.stopPropagation();
    /* 先由前端改地址栏：Streamlit 每次 rerun 都会用当前 URL 覆盖后端的
       query_params，只有前端先改，页面状态和地址栏才不会各说各话。 */
    var href = el.getAttribute('href') || '';
    var before = host.location.search;
    if (href.charAt(0) === '?') {
      try { host.history.pushState(null, '', href); } catch (err) {}
    }
    try { btn.click(); } catch (err) {
      try { host.history.replaceState(null, '', before || host.location.pathname); } catch (e2) {}
    }
  };
  doc.addEventListener('click', host.__hnClickHandler, true);
  host.__hnReady = true;
})();
</script>
"""


def begin() -> None:
    """每轮脚本开头调用：清空槽位并挂上点击桥。"""
    global _FLUSHED
    _SLOTS.clear()
    _INDEX.clear()
    _FLUSHED = False
    try:
        components.html(_BRIDGE_JS, height=0)
    except Exception:
        pass


def slot(
    params: dict | None = None,
    *,
    action=None,
    state: dict | None = None,
    dedupe: str = "",
) -> int:
    """登记一个跳转目标，返回槽位号。相同目标复用同一个槽位。"""
    if dedupe and dedupe in _INDEX:
        return _INDEX[dedupe]
    if len(_SLOTS) >= _MAX_SLOTS:
        return -1
    index = len(_SLOTS)
    _SLOTS.append({"params": params, "action": action, "state": state})
    if dedupe:
        _INDEX[dedupe] = index
    return index


def _params_from_href(href: str) -> tuple[dict, str]:
    """把 ``?page=qa&view=library#doc-1`` 拆成 (查询参数, 锚点)。"""
    split = urlsplit(href)
    params = {k: v for k, v in parse_qsl(split.query, keep_blank_values=True)}
    return params, split.fragment


def slot_for_href(href: str) -> int:
    """按 href 登记槽位（同地址复用）。"""
    params, anchor = _params_from_href(href)
    if not params:
        return -1
    if anchor:
        params["_h"] = anchor
    return slot(params, dedupe="href:" + href)


_ANCHOR_RE = re.compile(r"<a\b[^>]*>", re.IGNORECASE)
_HREF_RE = re.compile(r'href="([^"]*)"', re.IGNORECASE)


def _decorate_tag(tag: str) -> str:
    if "data-hn" in tag or "data-no-soft" in tag:
        return tag
    match = _HREF_RE.search(tag)
    if not match:
        return tag
    href = html.unescape(match.group(1))
    if not href.startswith("?"):
        return tag
    index = slot_for_href(href)
    if index < 0:
        return tag
    return re.sub(r"^<a\b", lambda m: f'{m.group(0)} data-hn="{index}"', tag, count=1)


def decorate(markup: str) -> str:
    """给富文本里的站内链接批量加上软跳转标记。"""
    if "href=\"?" not in markup:
        return markup
    return _ANCHOR_RE.sub(lambda m: _decorate_tag(m.group(0)), markup)


def link(
    inner: str,
    *,
    params: dict | None = None,
    action=None,
    state: dict | None = None,
    href: str = "#",
    cls: str = "",
    attrs: str = "",
    dedupe: str = "",
) -> str:
    """生成一个软跳转链接（保留 href 作为兜底）。"""
    index = slot(params, action=action, state=state, dedupe=dedupe)
    class_attr = f' class="{html.escape(cls, quote=True)}"' if cls else ""
    hn_attr = f' data-hn="{index}"' if index >= 0 else ""
    return (
        f'<a{class_attr}{hn_attr} href="{html.escape(href, quote=True)}" '
        f'target="_self" {attrs}>{inner}</a>'
    )


_PENDING_KEY = "_nav_pending_params"


def _apply(payload: dict) -> None:
    state = payload.get("state")
    if isinstance(state, dict):
        for key, value in state.items():
            st.session_state[key] = value
    action = payload.get("action")
    if callable(action):
        try:
            action()
        except Exception:
            pass
    params = payload.get("params")
    if params is not None:
        mapping = {str(k): str(v) for k, v in params.items()}
        # 回调阶段写 query_params 时，前端偶发不同步；同时留一份「待应用」，
        # 由脚本开头（consume_pending）再落一次，保证地址栏与页面一致。
        try:
            st.session_state[_PENDING_KEY] = mapping
        except Exception:
            pass
        try:
            st.query_params.from_dict(mapping)
        except Exception:
            try:
                st.query_params.clear()
                for key, value in mapping.items():
                    st.query_params[key] = value
            except Exception:
                pass


def consume_pending() -> None:
    """在脚本开头应用上一轮点击留下的查询参数（前端已先改好地址栏）。"""
    try:
        mapping = st.session_state.pop(_PENDING_KEY, None)
    except Exception:
        return
    if not isinstance(mapping, dict) or not mapping:
        return
    try:
        st.query_params.from_dict(mapping)
    except Exception:
        try:
            st.query_params.clear()
            for key, value in mapping.items():
                st.query_params[key] = value
        except Exception:
            pass


def flush() -> None:
    """页面末尾渲染隐藏的桥接按钮（必须晚于所有富文本渲染）。"""
    global _FLUSHED
    if _FLUSHED or not _SLOTS:
        return
    _FLUSHED = True
    try:
        with st.container(key="hn-bridge"):
            for index, payload in enumerate(_SLOTS):
                st.button(
                    f"·{index}",
                    key=f"hn-{index}",
                    on_click=_apply,
                    args=(payload,),
                )
    except Exception:
        pass
