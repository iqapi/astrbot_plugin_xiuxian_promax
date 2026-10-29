# managers/tournament_manager.py
"""斗法台锦标赛：周期性全自动单败淘汰赛（v3.21.0 新玩法）

节奏：
- 周一 00:00 ～ 周四 24:00 报名期（/斗法台 报名，报名费 5000，上限 32 人）
- 周五起任意一次主控定时检查触发 run()：按报名顺序配对（32/16/8 强补空位轮空），
  全部轮次用天道压制规则（combat_manager.player_vs_player_balanced）自动模拟，
  每轮之间无需玩家在线
- 奖励：冠军 10 万灵石 + 10 万修为；亚军 3 万灵石；四强各 1 万灵石
- 状态全存 system_config（JSON），周 key 隔离自动开新届
"""

import json
import random
import time
from typing import Tuple

from astrbot.api import logger

from ..data.data_manager import DataBase
from ..models import Player

__all__ = ["TournamentManager"]


class TournamentManager:
    """斗法台锦标赛"""

    ENTRY_FEE = 5000
    MAX_PLAYERS = 32
    SIGNUP_DAYS = (0, 1, 2, 3)   # 周一(0)～周四(3) 报名
    RUN_DAYS = (4, 5, 6)         # 周五(4)起可开赛
    CHAMPION_GOLD = 100000
    CHAMPION_EXP = 100000
    RUNNER_UP_GOLD = 30000
    SEMI_GOLD = 10000

    def __init__(self, db: DataBase):
        self.db = db

    # ===== 存取 =====

    def _week_key(self) -> str:
        return f"tnm_week_{time.strftime('%Y%W')}"

    async def _load_state(self) -> dict:
        raw = await self.db.ext.get_system_config(self._week_key())
        if not raw:
            return {"phase": "signup", "players": [], "champion": None, "log": []}
        try:
            data = json.loads(raw)
            return data if isinstance(data, dict) else {"phase": "signup", "players": []}
        except (json.JSONDecodeError, TypeError):
            return {"phase": "signup", "players": []}

    async def _save_state(self, state: dict):
        await self.db.ext.set_system_config(self._week_key(), json.dumps(state, ensure_ascii=False))

    def _weekday(self) -> int:
        return time.localtime().tm_wday

    # ===== 报名 =====

    async def signup(self, player: Player) -> Tuple[bool, str]:
        """/斗法台 报名
        v3.23.0：CAS 登记失败自动退费；并发报名不再吞钱"""
        if self._weekday() not in self.SIGNUP_DAYS:
            return False, "❌ 报名时间为每周一至周四，周五自动开赛。"
        state = await self._load_state()
        if state.get("phase") != "signup":
            return False, "❌ 本届锦标赛已开赛，请下届再来。"
        players = state.setdefault("players", [])
        if player.user_id in players:
            return False, "❌ 你已报名本届斗法台。"
        if len(players) >= self.MAX_PLAYERS:
            return False, f"❌ 报名已满（上限 {self.MAX_PLAYERS} 人）。"
        if player.gold < self.ENTRY_FEE:
            return False, f"❌ 报名费 {self.ENTRY_FEE:,} 灵石不足（当前持有 {player.gold:,}）。"

        # CAS 登记后再扣费；登记失败（并发冲突）不扣费直接重试提示
        new_state = dict(state)
        new_state["players"] = players + [player.user_id]
        registered = await self.db.ext.syscfg_cas(
            self._week_key(),
            json.dumps(new_state, ensure_ascii=False),
            json.dumps(state, ensure_ascii=False),
        )
        if not registered:
            return False, "⚔️ 报名瞬间人数激增，请再发一次 /斗法台 报名。"
        await self.db.add_player_gold(player.user_id, -self.ENTRY_FEE)
        return True, (
            f"⚔️ 报名成功！本届斗法台已有 {len(new_state['players'])}/{self.MAX_PLAYERS} 人。\n"
            f"━━━━━━━━━━━━━━━\n"
            f"周五自动开赛，天道压制规则（境界差距被抹平，人人有机会）。\n"
            f"冠军：{self.CHAMPION_GOLD:,} 灵石 + {self.CHAMPION_EXP:,} 修为！"
        )

    # ===== 开赛（定时触发） =====

    async def run(self) -> str:
        """主控定时调用：报名期结束（周五起）自动开赛。返回结算广播文本（空=无事）。
        v3.23.0：不再依赖当天 weekday——扫描所有未决届次（含停服跨周遗漏的旧 key），一律补开赛/退费。"""
        try:
            # 1) 当前周：到开赛日即开赛
            if self._weekday() in self.RUN_DAYS:
                state = await self._load_state()
                if state.get("phase") == "signup":
                    players = list(state.get("players", []))
                    if len(players) >= 2:
                        return await self._run_bracket(state, players)
                    if players:
                        # 人数不足：退回报名费
                        for uid in players:
                            await self.db.add_player_gold(uid, self.ENTRY_FEE)
                        state["phase"] = "done"
                        state["players"] = []
                        await self._save_state(state)
                        return f"⚔️ 本届斗法台报名不足 2 人，报名费已全数退回。"
                    state["phase"] = "done"
                    await self._save_state(state)
            # 2) 停服跨周兜底：扫描旧的未决届次（phase=signup 的历史周 key），退费了结
            async with self.db.conn.execute(
                "SELECT key, value FROM system_config WHERE key LIKE 'tnm_week_%'"
            ) as cursor:
                rows = await cursor.fetchall()
            current_key = self._week_key()
            for key, raw in rows:
                if key == current_key:
                    continue
                try:
                    old = json.loads(raw) if raw else None
                except Exception:
                    continue
                if isinstance(old, dict) and old.get("phase") == "signup" and old.get("players"):
                    for uid in old["players"]:
                        await self.db.add_player_gold(uid, self.ENTRY_FEE)
                    old["phase"] = "done"
                    old["players"] = []
                    await self.db.ext.set_system_config(key, json.dumps(old, ensure_ascii=False))
                    logger.info(f"[tournament] 遗漏届次已退费了结: {key}")
                    return f"⚔️ 上届斗法台因停服未能开赛，全部报名费已退回，敬请谅解。"
            return ""
        except Exception as e:
            logger.error(f"斗法台开赛异常: {e}")
            return ""

    async def _build_stats(self, player: Player):
        """按护镖/劫镖同款公式快速构建战斗属性"""
        from ..managers.combat_manager import CombatManager, CombatStats
        cm = CombatManager()
        hp, mp = cm.calculate_hp_mp(player.experience)
        atk = cm.calculate_atk(
            player.experience, player.atkpractice, 0,
            player.physical_damage, player.magic_damage, player.cultivation_type
        )
        return CombatStats(
            user_id=player.user_id, name=player.user_name or player.user_id[:8],
            hp=hp, max_hp=hp, mp=mp, max_mp=mp, atk=atk,
        )

    async def _run_bracket(self, state: dict, players: list) -> str:
        """配对 + 逐轮模拟 + 结算"""
        random.shuffle(players)
        # 补齐到 2 的幂：轮空
        size = 1
        while size < len(players):
            size *= 2
        bracket = players + [None] * (size - len(players))

        log_lines = []
        final_loser = None
        semi_losers = []
        round_no = 0
        while len([p for p in bracket if p]) > 1:
            round_no += 1
            next_round = []
            round_names = []
            is_final = len([p for p in bracket if p]) == 2
            is_semi = len([p for p in bracket if p]) == 4
            i = 0
            while i < len(bracket):
                a_id = bracket[i]
                b_id = bracket[i + 1] if i + 1 < len(bracket) else None
                i += 2
                if a_id is None and b_id is None:
                    continue
                if a_id is None:
                    next_round.append(b_id)
                    continue
                if b_id is None:
                    next_round.append(a_id)
                    round_names.append(f"{await self._name(a_id)} 轮空")
                    continue
                # 模拟一战
                pa = await self.db.get_player_by_id(a_id)
                pb = await self.db.get_player_by_id(b_id)
                if not pa and not pb:
                    continue
                if not pa:
                    next_round.append(b_id)
                    round_names.append(f"{await self._name(b_id)} 胜（对手失格）")
                    continue
                if not pb:
                    next_round.append(a_id)
                    round_names.append(f"{await self._name(a_id)} 胜（对手失格）")
                    continue
                s1 = await self._build_stats(pa)
                s2 = await self._build_stats(pb)
                result = self._combat().player_vs_player_balanced(s1, s2)
                winner = result.get("winner")
                if winner not in (a_id, b_id):
                    winner = random.choice([a_id, b_id])  # 平局随机
                loser = b_id if winner == a_id else a_id
                next_round.append(winner)
                round_names.append(f"{await self._name(winner)} 击败 {await self._name(loser)}")
                if is_final:
                    final_loser = loser
                elif is_semi:
                    semi_losers.append(loser)
            log_lines.append(f"【第{round_no}轮】" + "；".join(round_names))
            bracket = next_round + [None] * (len(next_round) % 2)

        champion = next((p for p in bracket if p), None)
        state["phase"] = "done"
        state["champion"] = champion
        state["runner_up"] = final_loser
        state["log"] = log_lines
        await self._save_state(state)

        # 发奖
        champ_name = "虚位"
        if champion:
            champ_name = await self._name(champion)
            await self.db.add_player_gold(champion, self.CHAMPION_GOLD)
            await self.db.add_player_exp(champion, self.CHAMPION_EXP)
        if final_loser:
            await self.db.add_player_gold(final_loser, self.RUNNER_UP_GOLD)
        for uid in semi_losers[:2]:
            await self.db.add_player_gold(uid, self.SEMI_GOLD)

        lines = [
            f"⚔️【斗法台锦标赛】落幕！",
            f"━━━━━━━━━━━━━━━",
        ]
        lines.extend(log_lines[-3:])
        lines.append("━━━━━━━━━━━━━━━")
        lines.append(f"🏆 本届冠军：【{champ_name}】")
        lines.append(f"奖励：{self.CHAMPION_GOLD:,} 灵石 + {self.CHAMPION_EXP:,} 修为！")
        lines.append(f"💡 下周一 /斗法台 报名，卷土重来！")
        return "\n".join(lines)

    def _combat(self):
        from ..managers.combat_manager import CombatManager
        return CombatManager()

    async def _name(self, uid: str) -> str:
        p = await self.db.get_player_by_id(uid)
        return (p.user_name if p else None) or uid[:8]

    # ===== 查询 =====

    async def handle_board(self, event) -> str:
        """/斗法台 查看状态"""
        state = await self._load_state()
        wd = self._weekday()
        phase = state.get("phase", "signup")
        lines = ["⚔️【斗法台锦标赛】", "━━━━━━━━━━━━━━━"]
        if phase == "signup":
            lines.append(f"📋 报名期（周一～周四）· 已报名 {len(state.get('players', []))}/{self.MAX_PLAYERS} 人")
            lines.append(f"💰 报名费 {self.ENTRY_FEE:,} 灵石 · 周五自动开赛")
            lines.append("💡 /斗法台 报名")
        elif phase == "done":
            champ = state.get("champion")
            champ_name = await self._name(champ) if champ else "虚位以待"
            lines.append(f"🏆 上届冠军：{champ_name}")
            lines.append("下周一重新开放报名。")
        if wd in self.RUN_DAYS and phase == "signup":
            lines.append("⚡ 周五已至，即将自动开赛！")
        lines.append("━━━━━━━━━━━━━━━")
        lines.append("规则：天道压制（境界抹平）单败淘汰，全服观战")
        return "\n".join(lines)
