# managers/bank_manager.py
"""灵石银行系统管理器 - 包含存取款、贷款、流水记录功能"""
import time
from decimal import Decimal, ROUND_DOWN
from typing import Tuple, List, Optional
from ..data import DataBase
from ..models import Player

__all__ = ["BankManager"]

# 银行配置默认值
DEFAULT_DAILY_INTEREST_RATE = 0.002  # 存款日利率 0.2%（v3.18.4 上调：存贷利差从 8 倍压到 2.5-4 倍的合理区间）
DEFAULT_MAX_DEPOSIT = 10000000  # 最大存款上限 1000万
DEFAULT_LOAN_INTEREST_RATE = 0.005  # 贷款日利率 0.5%
DEFAULT_LOAN_DURATION_DAYS = 7  # 贷款期限 7天
DEFAULT_MAX_LOAN_AMOUNT = 1000000  # 最大贷款额度 100万
DEFAULT_MIN_LOAN_AMOUNT = 1000  # 最小贷款额度 1000
DEFAULT_BREAKTHROUGH_LOAN_RATE = 0.008  # 突破贷款日利率 0.8%（更高风险）
DEFAULT_BREAKTHROUGH_LOAN_DURATION = 3  # 突破贷款期限 3天


class BankManager:
    """灵石银行管理器"""
    
    def __init__(self, db: DataBase, config: dict = None):
        self.db = db
        self.config = config or {}

        # 从配置读取，使用默认值作为后备。
        # v3.18.4 修复：game_config.json 中银行键是小写（daily_interest_rate），
        # 旧代码只按全大写读，配置文件从未生效过——现在两种键名都兼容
        bank_config = self.config.get("BANK", {}) or self.config.get("bank", {})
        # 第三优先级：_conf_schema.json VALUES 分组（WebUI 可调，v3.18.4 新增暴露）
        values = self.config.get("VALUES", {}) or {}
        def _cfg(upper: str, lower: str, default):
            return values.get(upper, bank_config.get(upper, bank_config.get(lower, default)))
        self.daily_interest_rate = _cfg("BANK_DAILY_INTEREST_RATE", "daily_interest_rate", DEFAULT_DAILY_INTEREST_RATE)
        self.max_deposit = _cfg("BANK_MAX_DEPOSIT", "max_deposit", DEFAULT_MAX_DEPOSIT)
        self.loan_interest_rate = _cfg("BANK_LOAN_INTEREST_RATE", "loan_interest_rate", DEFAULT_LOAN_INTEREST_RATE)
        self.loan_duration_days = _cfg("LOAN_DURATION_DAYS", "loan_duration_days", DEFAULT_LOAN_DURATION_DAYS)
        self.max_loan_amount = _cfg("BANK_MAX_LOAN_AMOUNT", "max_loan_amount", DEFAULT_MAX_LOAN_AMOUNT)
        self.min_loan_amount = _cfg("MIN_LOAN_AMOUNT", "min_loan_amount", DEFAULT_MIN_LOAN_AMOUNT)
        self.breakthrough_loan_rate = _cfg("BREAKTHROUGH_LOAN_RATE", "breakthrough_loan_rate", DEFAULT_BREAKTHROUGH_LOAN_RATE)
        self.breakthrough_loan_duration = _cfg("BREAKTHROUGH_LOAN_DURATION", "breakthrough_loan_duration", DEFAULT_BREAKTHROUGH_LOAN_DURATION)
    
    # ===== 存款相关 =====
    
    async def get_bank_info(self, player: Player) -> dict:
        """获取银行账户信息"""
        bank_data = await self.db.ext.get_bank_account(player.user_id)
        if not bank_data:
            bank_info = {"balance": 0, "last_interest_time": 0, "pending_interest": 0}
        else:
            pending_interest = self._calculate_interest(
                bank_data["balance"], 
                bank_data["last_interest_time"]
            )
            bank_info = {
                "balance": bank_data["balance"],
                "last_interest_time": bank_data["last_interest_time"],
                "pending_interest": pending_interest
            }
        
        loan = await self.db.ext.get_active_loan(player.user_id)
        bank_info["loan"] = loan
        
        return bank_info
    
    def _calculate_interest(self, balance: int, last_time: int) -> int:
        """计算待领利息（使用Decimal精确计算；复利天数封顶365天，防止长年不领无限滚存突破存款上限）"""
        if balance <= 0 or last_time <= 0:
            return 0

        now = int(time.time())
        days_passed = (now - last_time) // 86400

        if days_passed < 1:
            return 0
        days_passed = min(days_passed, 365)

        balance_d = Decimal(str(balance))
        rate_d = Decimal(str(self.daily_interest_rate))

        compound = (1 + rate_d) ** days_passed - 1
        interest = balance_d * compound

        return int(interest.quantize(Decimal('1'), rounding=ROUND_DOWN))
    
    async def deposit(self, player: Player, amount: int) -> Tuple[bool, str]:
        """存入灵石"""
        if amount <= 0:
            return False, "存款金额必须大于0。"
        
        await self.db.conn.execute("BEGIN IMMEDIATE")
        try:
            player = await self.db.get_player_by_id(player.user_id)
            if player.gold < amount:
                await self.db.conn.rollback()
                return False, f"灵石不足！你只有 {player.gold:,} 灵石。"
            
            bank_data = await self.db.ext.get_bank_account(player.user_id)
            current_balance = bank_data["balance"] if bank_data else 0
            
            if current_balance + amount > self.max_deposit:
                await self.db.conn.rollback()
                return False, f"存款上限为 {self.max_deposit:,} 灵石，当前余额 {current_balance:,}。"
            
            player.gold -= amount
            await self.db.update_player(player, commit=False)
            
            new_balance = current_balance + amount
            now = int(time.time())
            interest_time = now if current_balance == 0 else bank_data["last_interest_time"]
            
            # 直接底层 SQL 更新账户
            await self.db.conn.execute(
                "INSERT INTO bank_accounts (user_id, balance, last_interest_time) VALUES (?, ?, ?) ON CONFLICT(user_id) DO UPDATE SET balance = excluded.balance, last_interest_time = excluded.last_interest_time",
                (player.user_id, new_balance, interest_time)
            )
            
            # 直接底层 SQL 写流水
            await self.db.conn.execute(
                "INSERT INTO bank_transactions (user_id, trans_type, amount, balance_after, description, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (player.user_id, "deposit", amount, new_balance, "存入灵石", now)
            )
            
            await self.db.conn.commit()
            return True, f"成功存入 {amount:,} 灵石！\n当前余额：{new_balance:,} 灵石"
        except Exception as e:
            await self.db.conn.rollback()
            raise
    
    async def withdraw(self, player: Player, amount: int) -> Tuple[bool, str]:
        """取出灵石"""
        if amount <= 0:
            return False, "取款金额必须大于0。"
        
        await self.db.conn.execute("BEGIN IMMEDIATE")
        try:
            player = await self.db.get_player_by_id(player.user_id)
            bank_data = await self.db.ext.get_bank_account(player.user_id)
            if not bank_data or bank_data["balance"] < amount:
                await self.db.conn.rollback()
                current = bank_data["balance"] if bank_data else 0
                return False, f"余额不足！当前余额：{current:,} 灵石。"
            
            new_balance = bank_data["balance"] - amount
            now = int(time.time())
            
            await self.db.conn.execute(
                "INSERT INTO bank_accounts (user_id, balance, last_interest_time) VALUES (?, ?, ?) ON CONFLICT(user_id) DO UPDATE SET balance = excluded.balance, last_interest_time = excluded.last_interest_time",
                (player.user_id, new_balance, bank_data["last_interest_time"])
            )
            
            player.gold += amount
            await self.db.update_player(player, commit=False)
            
            await self.db.conn.execute(
                "INSERT INTO bank_transactions (user_id, trans_type, amount, balance_after, description, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (player.user_id, "withdraw", -amount, new_balance, "取出灵石", now)
            )
            
            await self.db.conn.commit()
            return True, f"成功取出 {amount:,} 灵石！\n当前余额：{new_balance:,} 灵石\n当前持有：{player.gold:,} 灵石"
        except Exception as e:
            await self.db.conn.rollback()
            raise
    
    async def claim_interest(self, player: Player) -> Tuple[bool, str]:
        """领取利息（事务化，防止并发双领）"""
        await self.db.conn.execute("BEGIN IMMEDIATE")
        try:
            # 事务内重读账户，确保利息以最新余额计算
            bank_data = await self.db.ext.get_bank_account(player.user_id)
            if not bank_data or bank_data["balance"] <= 0:
                await self.db.conn.rollback()
                return False, "你还没有存款，无法领取利息。"

            interest = self._calculate_interest(
                bank_data["balance"],
                bank_data["last_interest_time"]
            )

            if interest <= 0:
                await self.db.conn.rollback()
                return False, "利息不足1灵石，请明日再来。"

            new_balance = bank_data["balance"] + interest
            now = int(time.time())

            # 直接底层 SQL 更新账户（附带余额校验，防并发重复领取）
            cursor = await self.db.conn.execute(
                "UPDATE bank_accounts SET balance = ?, last_interest_time = ? "
                "WHERE user_id = ? AND balance = ? AND last_interest_time = ?",
                (new_balance, now, player.user_id, bank_data["balance"], bank_data["last_interest_time"])
            )
            if cursor.rowcount == 0:
                await self.db.conn.rollback()
                return False, "❌ 领取失败，账户刚发生变化，请重试。"

            # 写流水
            await self.db.conn.execute(
                "INSERT INTO bank_transactions (user_id, trans_type, amount, balance_after, description, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (player.user_id, "interest", interest, new_balance, "领取利息", now)
            )

            await self.db.conn.commit()

            return True, f"成功领取利息 {interest:,} 灵石！\n当前余额：{new_balance:,} 灵石"
        except Exception:
            await self.db.conn.rollback()
            raise
    
    # ===== 贷款相关 =====
    
    async def get_loan_info(self, player: Player) -> Optional[dict]:
        """获取贷款详情"""
        loan = await self.db.ext.get_active_loan(player.user_id)
        if not loan:
            return None
        
        now = int(time.time())
        days_borrowed = (now - loan["borrowed_at"]) // 86400
        days_remaining = max(0, (loan["due_at"] - now) // 86400)
        
        interest = int(loan["principal"] * loan["interest_rate"] * max(1, days_borrowed))
        total_due = loan["principal"] + interest
        
        is_overdue = now > loan["due_at"]
        
        return {
            **loan,
            "days_borrowed": days_borrowed,
            "days_remaining": days_remaining,
            "current_interest": interest,
            "total_due": total_due,
            "is_overdue": is_overdue
        }
    
    async def borrow(self, player: Player, amount: int, loan_type: str = "normal") -> Tuple[bool, str]:
        """申请贷款"""
        if amount < self.min_loan_amount:
            return False, f"最小贷款金额为 {self.min_loan_amount:,} 灵石。"
        
        if amount > self.max_loan_amount:
            return False, f"最大贷款金额为 {self.max_loan_amount:,} 灵石。"
        
        await self.db.conn.execute("BEGIN IMMEDIATE")
        try:
            player = await self.db.get_player_by_id(player.user_id)
            existing_loan = await self.db.ext.get_active_loan(player.user_id)
            if existing_loan:
                await self.db.conn.rollback()
                return False, "你已有未还清的贷款，请先还款后再申请新贷款。"
            
            if loan_type == "breakthrough":
                interest_rate = self.breakthrough_loan_rate
                duration_days = self.breakthrough_loan_duration
                type_name = "突破贷款"
            else:
                interest_rate = self.loan_interest_rate
                duration_days = self.loan_duration_days
                type_name = "普通贷款"
            
            now = int(time.time())
            due_at = now + duration_days * 86400
            
            # 直接底层 SQL 创建贷款
            await self.db.conn.execute(
                """INSERT INTO bank_loans (user_id, principal, interest_rate, borrowed_at, due_at, status, loan_type)
                   VALUES (?, ?, ?, ?, ?, 'active', ?)""",
                (player.user_id, amount, interest_rate, now, due_at, loan_type)
            )
            
            player.gold += amount
            await self.db.update_player(player, commit=False)
            
            bank_data = await self.db.ext.get_bank_account(player.user_id)
            balance = bank_data["balance"] if bank_data else 0
            
            await self.db.conn.execute(
                "INSERT INTO bank_transactions (user_id, trans_type, amount, balance_after, description, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (player.user_id, "loan", amount, balance, f"{type_name}：借入{amount:,}灵石", now)
            )
            
            total_interest = int(amount * interest_rate * duration_days)
            total_due = amount + total_interest
            
            await self.db.conn.commit()
            return True, (
                f"💰 {type_name}成功！\n"
                f"━━━━━━━━━━━━━━━\n"
                f"借入金额：{amount:,} 灵石\n"
                f"日利率：{interest_rate:.1%}\n"
                f"还款期限：{duration_days} 天\n"
                f"到期应还：约 {total_due:,} 灵石\n"
                f"━━━━━━━━━━━━━━━\n"
                f"当前持有：{player.gold:,} 灵石\n"
                f"💀 逾期将被银行追杀致死！"
            )
        except Exception as e:
            await self.db.conn.rollback()
            raise
    
    async def repay(self, player: Player) -> Tuple[bool, str]:
        """还款"""
        await self.db.conn.execute("BEGIN IMMEDIATE")
        try:
            player = await self.db.get_player_by_id(player.user_id)
            loan_info = await self.get_loan_info(player)
            if not loan_info:
                await self.db.conn.rollback()
                return False, "你当前没有需要偿还的贷款。"
            
            total_due = loan_info["total_due"]
            
            if player.gold < total_due:
                await self.db.conn.rollback()
                return False, (
                    f"灵石不足！\n"
                    f"应还金额：{total_due:,} 灵石\n"
                    f"（本金 {loan_info['principal']:,} + 利息 {loan_info['current_interest']:,}）\n"
                    f"当前持有：{player.gold:,} 灵石\n"
                    f"还差：{total_due - player.gold:,} 灵石"
                )
            
            player.gold -= total_due
            await self.db.update_player(player, commit=False)
            
            # 直接底层 SQL 关闭贷款
            await self.db.conn.execute("UPDATE bank_loans SET status = 'closed' WHERE id = ?", (loan_info["id"],))
            
            bank_data = await self.db.ext.get_bank_account(player.user_id)
            balance = bank_data["balance"] if bank_data else 0
            now = int(time.time())
            
            await self.db.conn.execute(
                "INSERT INTO bank_transactions (user_id, trans_type, amount, balance_after, description, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (player.user_id, "repay", -total_due, balance, f"还款：本金{loan_info['principal']:,}+利息{loan_info['current_interest']:,}", now)
            )
            
            loan_type_name = "突破贷款" if loan_info["loan_type"] == "breakthrough" else "普通贷款"
            
            await self.db.conn.commit()
            return True, (
                f"✅ 还款成功！\n"
                f"━━━━━━━━━━━━━━━\n"
                f"贷款类型：{loan_type_name}\n"
                f"已还本金：{loan_info['principal']:,} 灵石\n"
                f"已还利息：{loan_info['current_interest']:,} 灵石\n"
                f"合计支付：{total_due:,} 灵石\n"
                f"━━━━━━━━━━━━━━━\n"
                f"当前持有：{player.gold:,} 灵石"
            )
        except Exception as e:
            await self.db.conn.rollback()
            raise
    
    GRACE_PERIOD = 7 * 86400  # 逾期宽限期 7 天，宽限期内只催收不删号

    async def check_and_process_overdue_loans(self) -> List[dict]:
        """检查并处理逾期贷款：逾期先标记并催收，宽限期（7天）满仍未处理才注销角色"""
        now = int(time.time())
        overdue_loans = await self.db.ext.get_overdue_loans(now)
        processed = []

        for loan in overdue_loans:
            player = await self.db.get_player_by_id(loan["user_id"])
            if not player:
                await self.db.ext.mark_loan_overdue(loan["id"])
                continue

            player_name = player.user_name or f"道友{player.user_id[:6]}"
            overdue_days = (now - loan["due_at"]) // 86400

            if overdue_days < self.GRACE_PERIOD // 86400:
                # 宽限期内：保持 active（下轮检查会重新评估），只按天限流寄信催收，不动角色
                mail_key = f"loan_grace_mail_{loan['id']}_{time.strftime('%Y%m%d')}"
                if not await self.db.ext.get_system_config(mail_key):
                    await self.db.ext.set_system_config(mail_key, "1")
                    try:
                        from .enhance_systems import MailboxManager
                        await MailboxManager(self.db).send(
                            loan["user_id"], "银行催收函",
                            f"你的贷款已逾期 {overdue_days} 天！请在 {self.GRACE_PERIOD // 86400 - overdue_days} 天内 /还款，"
                            f"逾期超过 {self.GRACE_PERIOD // 86400} 天将被银行注销修籍！"
                        )
                    except Exception:
                        pass
                    # 仅当天首次催收时计入 processed，避免日志每小时重复计数
                    processed.append({
                        **loan,
                        "player_name": player_name,
                        "death": False,
                        "overdue_days": overdue_days
                    })
                continue

            await self.db.delete_player_cascade(player.user_id)
            await self.db.ext.mark_loan_overdue(loan["id"])

            # 写流水（角色已注销，流水保留作审计记录）
            await self.db.conn.execute(
                "INSERT INTO bank_transactions (user_id, trans_type, amount, balance_after, description, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (loan["user_id"], "bank_kill", 0, 0, f"逾期 {overdue_days} 天未还款，被银行注销修籍", int(time.time()))
            )
            await self.db.conn.commit()

            processed.append({
                **loan,
                "player_name": player_name,
                "death": True,
                "overdue_days": overdue_days
            })

        return processed
    
    # ===== 流水相关 =====
    
    async def get_transactions(self, user_id: str, limit: int = 20) -> List[dict]:
        """获取交易流水"""
        return await self.db.ext.get_bank_transactions(user_id, limit)
    
    # ===== 排行榜 =====
    
    async def get_deposit_ranking(self, limit: int = 10) -> List[dict]:
        """获取存款排行榜"""
        return await self.db.ext.get_deposit_ranking(limit)