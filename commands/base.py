# commands/base.py
"""指令装饰器公共设施（v3.24.0 自 main.py 拆出，供主类与各 Mixin 共用）"""
from functools import wraps

from astrbot.api.event import AstrMessageEvent


def require_whitelist(func):
    """装饰器：检查群聊白名单权限 + 强制指令前缀（/ 或 #）+ 指令参与度埋点"""
    @wraps(func)
    async def wrapper(self, event: AstrMessageEvent, *args, **kwargs):
        if not self._check_access(event):
            await self._send_access_denied_message(event)
            return
        # v3.25.1 封禁全覆盖：所有走装饰器的指令统一拦截（管理员豁免）
        try:
            uid = str(event.get_sender_id())
            if uid not in getattr(self, "boss_admins", []) and await self.db.ext.get_system_config(f"admin_ban_{uid}") == "1":
                yield event.plain_result("⛔ 你的账号已被天道封禁，如有异议请联系管理员。")
                return
        except Exception:
            pass
        # v3.24.0 参与度埋点（v3.25.1 走 GameStore 门面）
        try:
            from ..managers.game_store import GameStore
            GameStore(self.db).note_call(getattr(func, "_cmd_label", None) or func.__name__)
        except Exception:
            pass
        async for result in func(self, event, *args, **kwargs):
            yield result
    return wrapper


class CardMixin:
    """v3.25.0 通用文本→仙侠卡片适配器：任何返回纯文本的指令都能升级为图片卡片"""

    async def send_text_card(self, event: AstrMessageEvent, text: str, bg: str,
                             title: str, subtitle: str = "", footer: str = ""):
        """把多行文本渲染成卡片发送；渲染失败/关闭时回退原文。
        自动剔除 ━ 分隔线与首行同义标题（v3.25.1 改为精确同义，保留"第X届"等附加信息）。
        v3.25.1：上限提到 40 行，超出时在卡片尾部明确提示截断。"""
        try:
            from ..utils.image_generator import render_card_async
            lines = [ln.rstrip() for ln in (text or "").splitlines()]
            lines = [ln for ln in lines if ln.strip() and set(ln.strip()) != {"━"}]
            # 首行与卡片标题"完全同义"才去掉（核心字符相等），避免误删"第X届"等有效信息
            import re as _re
            def _core(s: str) -> str:
                return _re.sub(r'[^\w\u4e00-\u9fff]', '', s or '')
            if lines:
                head = _core(lines[0])
                title_core = _core(title)
                if head and title_core and (head == title_core or head in title_core):
                    lines = lines[1:]
            truncated = len(lines) > 40
            body = lines[:40]
            if truncated:
                body.append(f"⚠️ 内容较长，仅显示前 40 行（共 {len(lines)} 行）")
            path = await render_card_async(
                bg, title, subtitle,
                sections=[{"name": "详情", "rows": [], "lines": body}],
                footer=footer,
            )
            if path:
                yield event.image_result(path)
                return
        except Exception:
            pass
        yield event.plain_result(text)
