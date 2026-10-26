# managers/next_step.py
"""智能下一步提示系统 v6.19：根据玩家状态推荐合理的下一步指令"""
from typing import Optional

from ..data.data_manager import DataBase
from ..models import Player

__all__ = ["NextStepAdvisor"]


class NextStepAdvisor:
    def __init__(self, db: DataBase):
        self.db = db

    async def advise(self, player: Player, context: str = "") -> str:
        """根据玩家当前状态给出下一步建议。context = 触发场景"""
        level = player.level_index
        tips = []

        if context == "breakthrough":
            # 突破成功后：修为清零阶段 → 引导修为来源
            tips.append("💪 当前修为已消耗，快速回补途径：")
            tips.append("  · /闭关 挂机修炼（离线也有收益）")
            tips.append("  · /开始历练 （先发此指令看可用路线）")
            tips.append("  · /探索秘境 <ID>（修为+稀有掉落）")
            if level >= 3:
                tips.append("  · /服用丹药 <名>（丹药背包里的存货）")
            # 境界里程碑引导
            if level == 3:
                tips.append("🎓 恭喜踏入筑基！新解锁：/拜师 @人 拜师学艺、/押镖 镖行信约")
            elif level == 10:
                tips.append("🎓 金丹已成！可挑战更深的秘境与历练路线")
            elif level in (13, 16, 19, 22, 25, 28):
                tips.append("🎓 新的大境界！/称号图鉴 查看本境界专属称号，/宗门建筑 检查宗门加成")

        elif context == "cultivate":
            # 出关后：修为多了 → 引导突破或攒钱
            tips.append("📈 修为到手，接下来可以：")
            tips.append("  · /突破信息 查看距下次突破还差多少")
            tips.append("  · /接取任务 <黄/玄/地/天> 领日常任务")
            tips.append("  · /签到 /洞天收取 /收获 别忘了日常收菜")

        elif context == "adventure":
            tips.append("🗺️ 历练归来，接下来可以：")
            tips.append("  · /突破信息 看修为是否够突破")
            tips.append("  · /坊市 /丹阁 把战利品变现或补货")
            tips.append("  · /开始历练 继续下一趟（注意路线疲劳）")

        elif context == "rift":
            tips.append("🌀 秘境探索完成，接下来可以：")
            tips.append("  · /丹药背包 查看新到手的丹药")
            tips.append("  · /突破信息 修为可能够突破了")
            tips.append("  · /秘境列表 换个秘境继续")

        elif context == "checkin":
            tips.append("📅 签到完成，今日日常清单：")
            tips.append("  · /洞天收取 /收获 /灵眼收取")
            tips.append("  · /领取利息 /领取任务奖励")
            tips.append("  · /一键日常 可自动完成以上全部")

        if not tips:
            return ""
        return "\n\n💡【下一步】\n" + "\n".join(tips)
