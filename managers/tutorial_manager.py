# managers/tutorial_manager.py
from ..data import DataBase
from ..models import Player

class TutorialManager:
    def __init__(self, db: DataBase):
        self.db = db

    async def check_and_advance(self, player: Player, action_type: str) -> str:
        """检查是否可以推进新手引导，返回提示信息"""
        step = player.tutorial_step
        msg = ""
        exp_gain, gold_gain = 0, 0  # v3.25.5：奖励走原子记账

        if step == 0 and action_type == "create":
            player.tutorial_step = 1
            gold_gain = 1000
            msg = "\n\n🎓【新手引导】成功创建角色！奖励1000灵石。\n👉 下一步：发送 `/闭关` 体验修炼。"
        elif step == 1 and action_type == "cultivate":
            player.tutorial_step = 2
            exp_gain = 5000
            msg = "\n\n🎓【新手引导】完成闭关！奖励5000修为。\n👉 下一步：发送 `/开始历练 巡山问道` 体验冒险。"
        elif step == 2 and action_type == "adventure":
            player.tutorial_step = 3
            gold_gain = 5000
            msg = "\n\n🎓【新手引导】历练归来！奖励5000灵石。\n👉 下一步：发送 `/突破` 突破境界。"
        elif step == 3 and action_type == "breakthrough":
            player.tutorial_step = 4
            # 赠送一些基础装备或丹药（这里给修为）
            exp_gain = 10000
            msg = "\n\n🎓【新手引导】恭喜突破！奖励10000修为。\n🎉 你已完成全部新手引导，浩瀚仙途正式开启！"

        if msg:
            # v3.25.5：原子记账 + 定向落库（不再整行覆写快照）
            await self.db.update_player_fields(player.user_id, tutorial_step=player.tutorial_step)
            if exp_gain:
                await self.db.add_player_exp(player.user_id, exp_gain)
            if gold_gain:
                await self.db.add_player_gold(player.user_id, gold_gain)
        return msg