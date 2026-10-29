# managers/group_garden_manager.py
"""群聊灵植园 v1.0 - 每个群一块共享灵园，全群协力照料、按贡献分配灵石

约定：
- 状态全部存 system_config（JSON），不建新表
- 主控负责指令注册与群广播，本模块只做逻辑与文本
"""

import json
import time
from typing import Optional, Tuple, Dict

from astrbot.api import logger

from ..data.data_manager import DataBase
from ..models import Player

__all__ = ["GroupGardenManager", "GARDEN_CROPS"]


# ===== 作物表：需总照料人次 → 产出灵石池 =====
GARDEN_CROPS = {
    "青凝草":   {"need": 20, "pool": 8000,  "desc": "最常见的灵草，20 人次照料即熟"},
    "紫霄莲":   {"need": 35, "pool": 20000, "desc": "禀性娇贵，需 35 人次悉心照料"},
    "九叶灵芝": {"need": 50, "pool": 50000, "desc": "传说中的祥瑞，需 50 人次合力催熟"},
}

GARDEN_TEND_DAILY_LIMIT = 2  # 每人每天照料上限


def _today() -> str:
    """当天日期串（用于每人每日照料次数限流）"""
    return time.strftime("%Y-%m-%d")


class GroupGardenManager:
    """群聊共享灵园：种下 → 全群照料 → 成熟 → 按贡献人次分配灵石池"""

    def __init__(self, db: DataBase):
        self.db = db

    # ===== 存取 =====

    def _garden_key(self, group_id) -> str:
        return f"garden_{group_id}"

    async def _load_garden(self, group_id) -> Optional[Dict]:
        raw = await self.db.ext.get_system_config(self._garden_key(group_id))
        if not raw:
            return None
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError, ValueError):
            return None

    async def _save_garden(self, group_id, garden: Optional[Dict]):
        """garden 为 None 时清空该群园地"""
        await self.db.ext.set_system_config(self._garden_key(group_id), json.dumps(garden, ensure_ascii=False) if garden else "")

    @staticmethod
    def _total_tends(garden: Dict) -> int:
        return sum(garden.get("contributors", {}).values())

    # ===== 公开方法 =====

    async def get_garden(self, group_id) -> Optional[Dict]:
        """获取群灵园状态（无园地返回 None）"""
        try:
            return await self._load_garden(group_id)
        except Exception as e:
            logger.error(f"[群聊灵植园] 读取园地失败: {e}")
            return None

    async def plant(self, group_id, player: Player, crop_id: str) -> Tuple[bool, str]:
        """种下作物。园中已有作物未成熟时不可重种"""
        try:
            crop = GARDEN_CROPS.get(crop_id)
            if not crop:
                names = " / ".join(GARDEN_CROPS.keys())
                return False, f"❌ 没有名为【{crop_id}】的灵植。可选：{names}"

            garden = await self._load_garden(group_id)
            if garden and not garden.get("ready"):
                total = self._total_tends(garden)
                need = GARDEN_CROPS.get(garden.get("crop", ""), {"need": total})["need"]
                return False, (
                    f"🌱 园中已种着【{garden.get('crop')}】"
                    f"（{total}/{need} 人次），尚未成熟，不可重种。"
                )

            garden = {
                "crop": crop_id,
                "planted_at": int(time.time()),
                "planted_by": player.user_id,
                "planted_name": player.user_name,
                "contributors": {},
                "ready": False,
            }
            await self._save_garden(group_id, garden)
            return True, (
                f"🌱 {player.user_name} 在群灵植园种下了【{crop_id}】！\n"
                f"━━━━━━━━━━━━━━━\n"
                f"「{crop['desc']}」\n"
                f"成熟后产出灵石池：{crop['pool']:,} 灵石（按贡献人次分配）\n"
                f"💡 全群发送 /照料灵园 协力催熟（每人每天 2 次）"
            )
        except Exception as e:
            logger.error(f"[群聊灵植园] 种植失败: {e}")
            return False, "❌ 种植失败，请稍后再试。"

    async def tend(self, group_id, player: Player) -> Tuple[bool, str]:
        """照料灵园。每人每天限 2 次；达标时置 ready 并返回成熟提示"""
        try:
            garden = await self._load_garden(group_id)
            if not garden:
                return False, "🌰 灵园还是空地。发送 /灵植园 查看可种作物，由任意道友 /灵植园 种下 <名字> 开园。"
            if garden.get("ready"):
                return False, "✨ 园中【%s】已经成熟待收！发送 /收取灵园 分配灵石。" % garden.get("crop", "?")

            # 每日限流（v3.23.0 原子认领，并发不可绕过）
            limit_key = f"garden_tend_{player.user_id}_{_today()}"
            if not await self.db.ext.syscfg_claim_slot(limit_key, GARDEN_TEND_DAILY_LIMIT):
                return False, f"💦 你今天已照料 {GARDEN_TEND_DAILY_LIMIT} 次，灵力不济，明日再来吧（每日上限 {GARDEN_TEND_DAILY_LIMIT} 次）。"
            used = await self.db.ext.syscfg_get_number(limit_key)

            crop = GARDEN_CROPS.get(garden.get("crop", ""), {"need": 1, "pool": 0})
            contributors: Dict[str, int] = garden.setdefault("contributors", {})
            contributors[player.user_id] = contributors.get(player.user_id, 0) + 1
            total = self._total_tends(garden)
            garden["last_tend_name"] = player.user_name

            msg = f"💧 {player.user_name} 为【{garden.get('crop')}】灵植浇灌灵泉（今日第 {used} 次）。\n农事进度：{total}/{crop['need']} 人次"

            if total >= crop["need"]:
                garden["ready"] = True
                await self._save_garden(group_id, garden)
                return True, (
                    f"{msg}\n"
                    f"━━━━━━━━━━━━━━━\n"
                    f"🎉 灵气汇聚，【{garden.get('crop')}】硕果累累，灵园成熟了！\n"
                    f"📦 灵石池 {crop['pool']:,} 灵石待分配，参与照料的道友发送 /收取灵园 领取！"
                )
            await self._save_garden(group_id, garden)
            return True, msg
        except Exception as e:
            logger.error(f"[群聊灵植园] 照料失败: {e}")
            return False, "❌ 照料失败，请稍后再试。"

    async def harvest(self, group_id, player: Player) -> Tuple[bool, str]:
        """收取灵园：任何参与者可收，按贡献人次比例分配灵石池，发完清空园地
        v3.23.0：CAS 抢占清空——谁先把园地键清空谁组织分配，杜绝并发双发"""
        try:
            raw = await self.db.ext.get_system_config(f"garden_{group_id}")
            garden = None
            if raw:
                try:
                    garden = json.loads(raw)
                except (json.JSONDecodeError, TypeError):
                    garden = None
            if not garden:
                return False, "🌰 灵园还是空地，何来收获？发送 /灵植园 先种下灵植吧。"
            if not garden.get("ready"):
                total = self._total_tends(garden)
                crop = GARDEN_CROPS.get(garden.get("crop", ""), {"need": 1})
                return False, f"⏳ 【{garden.get('crop')}】尚未成熟（{total}/{crop['need']} 人次），继续照料吧。"

            crop = GARDEN_CROPS.get(garden.get("crop", ""), {"need": 1, "pool": 0})
            contributors: Dict[str, int] = garden.get("contributors", {})
            my_tends = contributors.get(player.user_id, 0)
            if my_tends < 1:
                return False, "🚫 你未参与过本轮照料（至少照料 1 次），无权收取。快去 /照料灵园 出一份力！"

            # CAS 抢占：以原 JSON 为期望值清空园地，成功者才分账
            claimed = await self.db.ext.syscfg_cas(f"garden_{group_id}", "", raw)
            if not claimed:
                return False, "🌾 手慢了！灵园刚被其他道友收取完毕。"

            pool = crop["pool"]
            total = self._total_tends(garden)
            lines = [f"🌾 【{garden.get('crop')}】丰收！灵石池 {pool:,} 灵石按贡献分配：", "━━━━━━━━━━━━━━━"]

            # 逐人发放（贡献人次 / 总人次 × 池子）
            for uid, tends in contributors.items():
                if tends < 1:
                    continue
                share = int(pool * tends / total)
                await self.db.add_player_gold(uid, share)
                # 尽量显示道号，查不到就用 UID 尾号
                name = uid[-4:]
                try:
                    p = await self.db.get_player_by_id(uid)
                    if p:
                        name = p.user_name
                except Exception:
                    pass
                lines.append(f"💧 {name}（贡献 {tends} 次）→ {share:,} 灵石")
            lines.append("━━━━━━━━━━━━━━━")
            lines.append(f"倡议人：{garden.get('planted_name', '匿名道友')} · 本次共 {total} 人次协力 🙌")
            return True, "\n".join(lines)
        except Exception as e:
            logger.error(f"[群聊灵植园] 收取失败: {e}")
            return False, "❌ 收取失败，请稍后再试。"

    async def handle_garden(self, group_id, event) -> str:
        """/灵植园 查看灵园状态（无参）或种植（/灵植园 种下 <作物名>）"""
        gid = group_id or (event.get_group_id() if event else None)
        if not gid:
            return "🌿 群聊灵植园仅支持群聊使用，私聊不可用。"

        msg = (getattr(event, "message_str", "") or "").strip() if event else ""
        parts = msg.replace("　", " ").split()
        garden = await self.get_garden(gid)

        # /灵植园 种下 <作物名>
        if len(parts) >= 2 and parts[1] in ("种下", "种植", "种"):
            if len(parts) < 3:
                return "❌ 用法：/灵植园 种下 <作物名>\n可选：" + " / ".join(GARDEN_CROPS.keys())
            # 种植需要玩家对象
            player = None
            uid = getattr(event, "get_sender_id", lambda: None)()
            if uid:
                player = await self.db.get_player_by_id(str(uid))
            if not player:
                return "❌ 未找到你的修仙档案，请先 /我的信息 创建角色。"
            ok, text = await self.plant(gid, player, parts[2])
            return text

        # 无参：查看状态
        if not garden:
            lines = ["🌿 群聊灵植园", "━━━━━━━━━━━━━━━", "🌰 本群灵园还是一片空地。"]
        else:
            crop = GARDEN_CROPS.get(garden.get("crop", ""), {"need": 1, "pool": 0, "desc": ""})
            total = self._total_tends(garden)
            lines = [
                "🌿 群聊灵植园",
                "━━━━━━━━━━━━━━━",
                f"🌱 当前作物：【{garden.get('crop')}】",
                f"📜 {crop['desc']}",
                f"🪣 灵石池：{crop['pool']:,} 灵石",
                f"💚 照料进度：{total}/{crop['need']} 人次",
            ]
            if garden.get("ready"):
                lines.append("✨ 状态：已成熟！参与者发送 /收取灵园 分配灵石")
            else:
                contributors = garden.get("contributors", {})
                top = sorted(contributors.items(), key=lambda kv: -kv[1])[:3]
                if top:
                    lines.append("🏆 照料榜：" + "、".join(f"{uid[-4:]}×{n}" for uid, n in top))
                lines.append(f"💡 /照料灵园 出力（每人每日 {GARDEN_TEND_DAILY_LIMIT} 次）")
        lines.append("━━━━━━━━━━━━━━━")
        lines.append("📖 作物一览：")
        for name, c in GARDEN_CROPS.items():
            lines.append(f"  【{name}】需 {c['need']} 人次 → {c['pool']:,} 灵石")
        return "\n".join(lines)
