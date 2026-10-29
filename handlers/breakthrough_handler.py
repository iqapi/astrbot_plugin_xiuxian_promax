# handlers/breakthrough_handler.py

from astrbot.api.event import AstrMessageEvent
from ..data import DataBase
from ..core import BreakthroughManager, PillManager
from ..config_manager import ConfigManager
from ..models import Player
from .utils import player_required

CMD_BREAKTHROUGH = "突破"
CMD_BREAKTHROUGH_INFO = "突破信息"

__all__ = ["BreakthroughHandler"]


class BreakthroughHandler:
    """突破系统处理器"""

    def __init__(self, db: DataBase, config_manager: ConfigManager, config: dict):
        self.db = db
        self.config_manager = config_manager
        self.config = config
        self.breakthrough_manager = BreakthroughManager(db, config_manager, config)
        self.pill_manager = PillManager(db, config_manager)

    @player_required
    async def handle_breakthrough_info(self, player: Player, event: AstrMessageEvent):
        """查看突破信息"""
        display_name = event.get_sender_name()

        # 根据修炼类型获取对应的境界数据
        level_data = self.config_manager.get_level_data(player.cultivation_type)

        # 检查是否已经是最高境界
        if player.level_index >= len(level_data) - 1:
            yield event.plain_result("你已经达到了最高境界，无法继续突破！")
            return

        await self.pill_manager.update_temporary_effects(player)
        modifiers = self.pill_manager.get_breakthrough_modifiers(player)

        # 获取当前和下一境界信息
        current_level_data = level_data[player.level_index]
        next_level_data = level_data[player.level_index + 1]

        current_level_name = current_level_data["level_name"]
        next_level_name = next_level_data["level_name"]
        required_exp = next_level_data.get("exp_needed", 0)
        base_success_rate = next_level_data.get("success_rate", 0.5)
        temp_bonus = modifiers["temp_bonus"]

        # 检查修为是否满足
        exp_satisfied = player.experience >= required_exp
        exp_status = "✅ 满足" if exp_satisfied else "❌ 不足"

        # 查找适用的破境丹
        available_pills = []
        for pill_name, pill_data in self.config_manager.pills_data.items():
            if (pill_data.get("subtype") == "breakthrough" and
                pill_data.get("target_level_index") == player.level_index + 1):
                max_rate = pill_data.get("max_success_rate", 1.0)
                breakthrough_bonus = pill_data.get("breakthrough_bonus", 0)
                final_rate = min(base_success_rate + temp_bonus + breakthrough_bonus, max_rate)
                available_pills.append({
                    "name": pill_name,
                    "rank": pill_data.get("rank", ""),
                    "final_rate": final_rate,
                    "max_rate": max_rate
                })

        # 构建信息显示
        info_lines = [
            f"=== {display_name} 的突破信息 ===\n",
            f"当前境界：{current_level_name}\n",
            f"下一境界：{next_level_name}\n",
            f"━━━━━━━━━━━━━━━\n",
            f"【突破条件】\n",
            f"所需修为：{required_exp}\n",
            f"当前修为：{player.experience}\n",
            f"修为状态：{exp_status}\n",
            f"突破资费：{self.breakthrough_manager.get_breakthrough_cost(player)} 灵石（成败皆不退，当前持有 {player.gold}）\n",
            f"━━━━━━━━━━━━━━━\n",
            f"【突破成功率】\n",
            f"基础成功率：{base_success_rate:.1%}\n",
        ]

        if temp_bonus:
            info_lines.append(f"临时丹药加成：{temp_bonus:+.1%}\n")
        karma = getattr(player, "karma", 0) or 0
        if karma != 0:
            karma_bonus = max(-0.10, min(0.10, karma * 0.01))
            if karma > 0:
                info_lines.append(f"功德庇佑：{karma_bonus:+.1%}（功德 {karma}）\n")
            else:
                info_lines.append(f"业力缠身：{karma_bonus:+.1%}（业力 {karma}，/行善 可消解）\n")
        # 连败保底与渡劫道韵
        try:
            import json as _json
            _pb = _json.loads(player.permanent_bonus) if player.permanent_bonus else {}
            _streak = int(_pb.get("bt_fail_streak", 0))
            if _streak >= 1:
                info_lines.append(f"🌟 道心磨砺：连败{_streak}次" + ("（下次+15%）" if _streak >= 3 else "（3次后每次+15%）") + "\n")
            if player.level_index >= 30:
                _dy = int(_pb.get("daoyun", 0))
                _g = int(_pb.get("daoyun_guarantee", 0))
                if _g:
                    info_lines.append("🌠 道韵已圆满：下次突破【必定成功】！\n")
                elif _dy > 0:
                    info_lines.append(f"🌠 渡劫道韵：{_dy}/100（满后必成）\n")
        except Exception:
            pass
        death_reduce = 1 - modifiers["permanent_death_multiplier"]
        if death_reduce > 0:
            info_lines.append(f"突破死亡概率降低：{death_reduce:.1%}\n")

        if available_pills:
            info_lines.append(f"\n【可用破境丹】\n")
            for pill in available_pills:
                info_lines.append(
                    f"• {pill['name']}（{pill['rank']}）\n"
                    f"  使用后成功率：{pill['final_rate']:.1%}（最高{pill['max_rate']:.1%}）\n"
                )
        else:
            info_lines.append(f"\n暂无适用的破境丹\n")

        # 根据修炼类型显示不同的突破说明
        if player.cultivation_type == "体修":
            info_lines.extend([
                f"━━━━━━━━━━━━━━━\n",
                f"【突破说明】\n",
                f"• 使用命令：{CMD_BREAKTHROUGH} 或 {CMD_BREAKTHROUGH} [破境丹名称]\n",
                f"• 突破成功：境界提升，肉身更强\n",
                f"• 突破失败：损失10%修为，有概率死亡\n",
                f"• 死亡后：所有数据清除，需重新入仙途\n",
                f"=" * 28
            ])
        else:
            info_lines.extend([
                f"━━━━━━━━━━━━━━━\n",
                f"【突破说明】\n",
                f"• 使用命令：{CMD_BREAKTHROUGH} 或 {CMD_BREAKTHROUGH} [破境丹名称]\n",
                f"• 突破成功：境界提升，实力大增\n",
                f"• 突破失败：损失10%修为，有概率死亡\n",
                f"• 死亡后：所有数据清除，需重新入仙途\n",
                f"=" * 28
            ])

        yield event.plain_result("".join(info_lines))

    @player_required
    async def handle_breakthrough(self, player: Player, event: AstrMessageEvent, pill_name: str = None):
        """执行突破"""
        display_name = event.get_sender_name()

        await self.pill_manager.update_temporary_effects(player)
        modifiers = self.pill_manager.get_breakthrough_modifiers(player)

        # 根据修炼类型获取对应的境界数据
        level_data = self.config_manager.get_level_data(player.cultivation_type)

        # 如果指定了破境丹，验证其有效性
        if pill_name and pill_name.strip():
            pill_name = pill_name.strip()
            pill_data = self.config_manager.pills_data.get(pill_name)

            if not pill_data:
                # 列出适用于当前突破的破境丹，便于玩家对照
                suitable = [
                    name for name, d in self.config_manager.pills_data.items()
                    if d.get("subtype") == "breakthrough" and d.get("target_level_index") == player.level_index + 1
                ]
                hint = "、".join(suitable) if suitable else "暂无（可直接空手突破）"
                yield event.plain_result(
                    f"❌ 未找到丹药：{pill_name}\n"
                    f"💡 适用于你本次突破的破境丹：{hint}\n"
                    f"💡 也可发送 /丹药背包 查看身上已有的丹药"
                )
                return

            if pill_data.get("subtype") != "breakthrough":
                yield event.plain_result(
                    f"❌ 【{pill_name}】不是破境丹（它是：{pill_data.get('subtype', '其他')}类丹药）。\n"
                    f"💡 请从 /丹药背包 中选择 subtype 为突破丹的丹药"
                )
                return

            # 检查是否适用于当前突破
            target_level = pill_data.get("target_level_index", -1)
            if target_level != player.level_index + 1:
                current_level = level_data[player.level_index]["level_name"]
                # 获取丹药目标境界名称
                target_level_name = f"境界{target_level}"
                if 0 <= target_level < len(level_data):
                    target_level_name = level_data[target_level]["level_name"]
                yield event.plain_result(
                    f"❌ {pill_name} 不适用于当前突破\n"
                    f"当前境界：{current_level}\n"
                    f"此丹药用于突破到：【{target_level_name}】"
                )
                return

            yield event.plain_result(f"使用【{pill_name}】进行突破...")
        else:
            pill_name = None
            yield event.plain_result("开始尝试突破...")

        # 执行突破
        success, message, died = await self.breakthrough_manager.execute_breakthrough(
            player,
            pill_name,
            modifiers["temp_bonus"],
            modifiers["permanent_death_multiplier"]
        )

        if modifiers["has_temp_effects"]:
            await self.pill_manager.consume_breakthrough_effects(player)

        yield event.plain_result(message)
