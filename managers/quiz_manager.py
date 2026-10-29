# managers/quiz_manager.py
"""修仙科举（v3.20.0 新玩法）

每日 3 次开考机会，每次从题库随机抽 3 题连环作答：
- 状态全部存 system_config（不建新表）
- 答对立即给满额修为奖励，答错不得分
- 会话 300 秒过期，过期作废需重新开考
"""

import json
import time
import random
from typing import Tuple, Optional

from astrbot.api import logger

from ..data.data_manager import DataBase
from ..models import Player

__all__ = ["QuizManager"]


class QuizManager:
    """修仙科举：题库抽题 + 连环答题 + 修为奖励"""

    DAILY_LIMIT = 3          # 每日开考次数上限
    QUESTIONS_PER_ROUND = 3  # 每次开考题数
    SESSION_EXPIRE = 300     # 会话过期（秒）

    # ================= 内置题库（answer 为选项下标，exp 按难度 500-3000） =================
    QUIZ_BANK = [
        # ---- 修仙常识 ----
        {"q": "修仙者突破境界时最怕的心魔，本质上是什么？",
         "options": ["体内淤积的怨气", "道心不坚定产生的执念", "天劫残留的雷气", "丹药服用过量的毒素"],
         "answer": 1, "exp": 500},
        {"q": "传说中的「辟谷」，指的是修仙者达到什么状态？",
         "options": ["不食五谷，以灵气为食", "在山谷中闭关", "永远不再进食", "只能喝水度日"],
         "answer": 0, "exp": 500},
        {"q": "修仙界常说「金丹大成」，金丹结于何处？",
         "options": ["识海之中", "丹田之内", "心脏之中", "眉心之间"],
         "answer": 1, "exp": 500},
        {"q": "「元婴」指的是什么？",
         "options": ["一件法宝的器灵", "修士孕育出的第二个自己（婴儿状的元神）", "丹药炼成的婴儿", "灵宠的幼年形态"],
         "answer": 1, "exp": 800},
        {"q": "修仙者飞升一般要去往哪里？",
         "options": ["海底龙宫", "地府轮回", "仙界（上界）", "西域佛国"],
         "answer": 2, "exp": 500},
        {"q": "灵根资质通常分为哪几种属性？",
         "options": ["金银铜铁锡", "金木水火土", "风雨雷电雪", "日月星辰辰"],
         "answer": 1, "exp": 500},
        {"q": "修仙小说中常见的「洞天福地」是什么？",
         "options": ["妖兽的巢穴", "灵气浓郁的修炼宝地", "凡人的村落", "销赃的黑市"],
         "answer": 1, "exp": 500},
        {"q": "「夺舍」在修仙界是什么行为？",
         "options": ["抢占他人肉身以魂魄寄居", "抢夺他人储物戒", "偷学他人功法", "强占他人洞府"],
         "answer": 0, "exp": 800},
        {"q": "修仙者为什么追求长生？",
         "options": ["为了当皇帝", "为了摆脱寿元大限，逍遥天地", "为了囤积灵石", "为了统御凡人"],
         "answer": 1, "exp": 500},
        {"q": "「闭关」的意思是？",
         "options": ["关闭山门不接待客人", "长时间静修不问外事", "关闭洞府的阵法", "隐姓埋名当凡人"],
         "answer": 1, "exp": 500},

        # ---- 五行相克 ----
        {"q": "五行相克中，「金」克什么？",
         "options": ["木", "水", "火", "土"],
         "answer": 0, "exp": 500},
        {"q": "五行相克中，「水」克什么？",
         "options": ["金", "木", "火", "土"],
         "answer": 2, "exp": 500},
        {"q": "五行相生中，「木」生什么？",
         "options": ["火", "水", "金", "土"],
         "answer": 0, "exp": 500},
        {"q": "五行相生中，「土」生什么？",
         "options": ["木", "火", "水", "金"],
         "answer": 3, "exp": 500},
        {"q": "火灵根修士对阵水灵根修士，一般谁占优？",
         "options": ["火灵根", "水灵根", "平手", "看谁嗓门大"],
         "answer": 1, "exp": 800},
        {"q": "五行相克顺序正确的一组是？",
         "options": ["金克木、木克土、土克水、水克火、火克金", "金克水、水克火、火克木、木克土、土克金", "金克火、火克水、水克土、土克木、木克金", "五行互相都不克"],
         "answer": 0, "exp": 1000},
        {"q": "五行相生顺序正确的一组是？",
         "options": ["金生木、木生水、水生火、火生土、土生金", "金生水、水生木、木生火、火生土、土生金", "金生火、火生木、木生土、土生水、水生金", "五行互相都不生"],
         "answer": 1, "exp": 1000},

        # ---- 境界常识 ----
        {"q": "修仙常见境界排序（由低到高）正确的是？",
         "options": ["筑基 → 练气 → 金丹 → 元婴", "练气 → 筑基 → 金丹 → 元婴", "金丹 → 练气 → 筑基 → 元婴", "元婴 → 金丹 → 筑基 → 练气"],
         "answer": 1, "exp": 800},
        {"q": "练气期修士与金丹期修士正面硬拼，结局大概率是？",
         "options": ["练气获胜", "五五开", "金丹碾压获胜", "同归于尽"],
         "answer": 2, "exp": 500},
        {"q": "「化神期」之上常见的境界是？",
         "options": ["练气期", "合体期/大乘期", "筑基期", "开光期"],
         "answer": 1, "exp": 800},
        {"q": "「渡劫」指的是修士在突破时经历什么？",
         "options": ["抢劫其他修士", "天劫雷罚的考验", "渡过一条天河", "宗门的长老考核"],
         "answer": 1, "exp": 500},
        {"q": "一般而言，寿元最长的是哪个阶段的修士？",
         "options": ["练气期", "筑基期", "金丹期", "渡劫飞升前的大乘期"],
         "answer": 3, "exp": 1000},
        {"q": "「散修」指的是？",
         "options": ["宗门里管打扫的杂役", "不加入宗门、独自修行的修士", "四处游历的凡人商贩", "被逐出家族的庶子"],
         "answer": 1, "exp": 500},

        # ---- 游戏机制题 ----
        {"q": "本游戏中「灵石」的主要用途是什么？",
         "options": ["装饰头像", "购买物品、押镖、悬赏等货币消费", "兑换现实钞票", "喂给灵宠当零食"],
         "answer": 1, "exp": 500},
        {"q": "本游戏中「修为」的作用是？",
         "options": ["累计到阈值即可突破境界", "直接兑换灵石", "提升魅力值", "增加寿命上限之外毫无用处"],
         "answer": 0, "exp": 500},
        {"q": "满级押镖一轮约 30 分钟，收益大约是多少灵石？",
         "options": ["200 灵石", "2,000 灵石", "20,000 灵石", "200,000 灵石"],
         "answer": 2, "exp": 1000},
        {"q": "本游戏专注一日（疯狂修炼）的修为产出大约在什么量级？",
         "options": ["90 万 - 100 万", "9 千 - 1 万", "9 百 - 1 千", "9 亿 - 10 亿"],
         "answer": 0, "exp": 1500},
        {"q": "想查看本游戏所有修仙指令，应该用什么？",
         "options": ["/修仙帮助", "/客服投诉", "/重启服务器", "/念咒语"],
         "answer": 0, "exp": 500},
        {"q": "本游戏中「五行灵根」影响的主要是什么？",
         "options": ["聊天字体颜色", "修炼属性与相克战斗表现", "商店打折力度", "群聊排序"],
         "answer": 1, "exp": 800},
        {"q": "修仙科举每日最多可开考几次？",
         "options": ["1 次", "3 次", "10 次", "无限次"],
         "answer": 1, "exp": 3000},
        {"q": "科举答题会话开启后多久不作答会过期？",
         "options": ["30 秒", "5 分钟（300 秒）", "1 小时", "永不过期"],
         "answer": 1, "exp": 2000},
    ]

    LETTERS = ["A", "B", "C", "D"]

    def __init__(self, db: DataBase):
        self.db = db

    # ================= 内部工具 =================

    def _cnt_key(self, uid: str) -> str:
        return f"quiz_cnt_{uid}_{time.strftime('%Y%m%d')}"

    def _session_key(self, uid: str) -> str:
        return f"quiz_session_{uid}"

    async def _get_cnt(self, uid: str) -> int:
        try:
            raw = await self.db.ext.get_system_config(self._cnt_key(uid))
            return int(raw) if raw else 0
        except Exception:
            return 0

    async def _load_session(self, uid: str) -> Optional[dict]:
        try:
            raw = await self.db.ext.get_system_config(self._session_key(uid))
            data = json.loads(raw) if raw else None
            if not isinstance(data, dict):
                return None
            # 300 秒过期
            if int(time.time()) - int(data.get("start_ts", 0)) > self.SESSION_EXPIRE:
                await self.db.ext.set_system_config(self._session_key(uid), "")
                return None
            return data
        except Exception as e:
            logger.warning(f"[quiz] 读取会话失败: {e}")
            return None

    async def _save_session(self, uid: str, session: Optional[dict]):
        value = json.dumps(session, ensure_ascii=False) if session else ""
        await self.db.ext.set_system_config(self._session_key(uid), value)

    # ================= 核心接口 =================

    async def start(self, player: Player) -> Tuple[bool, str]:
        """/科举 开考：每日 3 次，每次随机 3 题连环作答"""
        uid = player.user_id
        # 已有进行中的会话 → 直接续答，不消耗次数
        session = await self._load_session(uid)
        if session and len(session.get("answers_given", {})) < self.QUESTIONS_PER_ROUND:
            return True, self._render_questions(session, "📋 你还有未答完的科举题，继续作答：")

        # v3.23.0 原子认领场次（并发连发不可绕过每日限次）
        if not await self.db.ext.syscfg_claim_slot(self._cnt_key(uid), self.DAILY_LIMIT):
            return False, (
                f"❌ 今日科举已考满 {self.DAILY_LIMIT} 次，明日再战！\n"
                "💡 修仙重在平日积累，何不去闭关修炼？"
            )
        cnt = await self.db.ext.syscfg_get_number(self._cnt_key(uid))

        # 随机抽题（不重复）
        questions = random.sample(self.QUIZ_BANK, self.QUESTIONS_PER_ROUND)
        session = {
            "questions": [
                {"q": q["q"], "options": q["options"], "answer": q["answer"], "exp": q["exp"]}
                for q in questions
            ],
            "answers_given": {},   # {"1": "A", ...}
            "results": {},         # {"1": true/false, ...}
            "start_ts": int(time.time()),
        }
        try:
            await self._save_session(uid, session)
        except Exception as e:
            logger.error(f"[quiz] 保存会话失败: {e}")
            return False, "❌ 科举考场故障，请稍后再试。"

        return True, self._render_questions(
            session,
            f"🖋️【修仙科举】第 {cnt}/{self.DAILY_LIMIT} 场开考！\n共 {self.QUESTIONS_PER_ROUND} 题，限时 {self.SESSION_EXPIRE // 60} 分钟，答对即得修为！"
        )

    def _render_questions(self, session: dict, header: str) -> str:
        lines = [header, "━━━━━━━━━━━━━━━"]
        for idx, q in enumerate(session["questions"], start=1):
            no = str(idx)
            if no in session.get("answers_given", {}):
                mark = "✅" if session["results"].get(no) else "❌"
                lines.append(f"{mark} 第{idx}题（已答：{session['answers_given'][no]}）")
                continue
            lines.append(f"📖 第{idx}题（{q['exp']}修为）：{q['q']}")
            for li, opt in enumerate(q["options"]):
                lines.append(f"   {self.LETTERS[li]}. {opt}")
        answered = len(session.get("answers_given", {}))
        if answered < len(session["questions"]):
            lines.append("━━━━━━━━━━━━━━━")
            lines.append("💡 请用 /答题 <题号> <ABCD> 作答（如 /答题 1 B）")
        return "\n".join(lines)

    async def answer(self, player: Player, question_no: int, choice: str) -> Tuple[bool, str]:
        """/答题 <题号> <ABCD>：判对错立即发修为奖励，三题答完返回总结"""
        uid = player.user_id
        session = await self._load_session(uid)
        if not session:
            return False, "❌ 你当前没有进行中的科举。先用 /科举 开考吧！"

        no = str(question_no)
        questions = session.get("questions", [])
        if not (1 <= question_no <= len(questions)):
            return False, f"❌ 题号需在 1 - {len(questions)} 之间。"
        if no in session.get("answers_given", {}):
            return False, f"❌ 第 {question_no} 题已经作答过了。"

        choice = (choice or "").strip().upper()
        if choice not in self.LETTERS:
            return False, "❌ 选项需为 A / B / C / D。"

        q = questions[question_no - 1]
        correct = self.LETTERS.index(choice) == q["answer"]
        gained = q["exp"] if correct else 0

        # 修为奖励：科举奖励走 experience 累加后 update_player
        if gained > 0:
            player.experience += gained
            await self.db.update_player(player)

        session.setdefault("answers_given", {})[no] = choice
        session.setdefault("results", {})[no] = correct

        lines = [
            (f"✅ 第{question_no}题回答正确！获得科举奖励：修为 +{gained:,}"
             if correct else
             f"❌ 第{question_no}题回答错误。正确答案是 {self.LETTERS[q['answer']]}. {q['options'][q['answer']]}（无修为奖励）"),
        ]

        # 三题答完 → 总结并清场
        if len(session["answers_given"]) >= len(questions):
            right = sum(1 for v in session["results"].values() if v)
            total_exp = sum(
                questions[int(k) - 1]["exp"]
                for k, v in session["results"].items() if v
            )
            await self._save_session(uid, None)
            name = player.user_name or uid[:8]
            if right == len(questions):
                rank = "🏆 状元之才！"
            elif right >= 2:
                rank = "🎉 榜眼可期！"
            else:
                rank = "📚 尚需勤修。"
            lines += [
                "━━━━━━━━━━━━━━━",
                f"🖋️【科举放榜】{name}",
                f"答对：{right}/{len(questions)} 题 · 共获修为：{total_exp:,}",
                rank,
                "💡 今日还可用 /科举 再考（每日共 3 次）" if await self._get_cnt(uid) < self.DAILY_LIMIT
                else "💡 今日次数已用完，明日再来！",
            ]
        else:
            await self._save_session(uid, session)
            lines += ["━━━━━━━━━━━━━━━", self._render_questions(session, "继续作答剩余题目：").split("\n", 1)[1]]

        return True, "\n".join(lines)

    # ================= 指令入口 =================

    async def handle_quiz(self, player: Player, event):
        """/科举 无参即开考"""
        ok, msg = await self.start(player)
        yield event.plain_result(msg)
