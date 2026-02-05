#!/usr/bin/env python3
"""
Position Sizing Calculator for STOXX50 Iron Condor.
Calculates optimal position size based on account balance and risk parameters.
"""

from dataclasses import dataclass
from typing import Dict, Any, Optional


@dataclass
class PositionSize:
    """Calculated position size for a trade."""
    spreads: int
    contracts_per_spread: int
    max_loss_per_spread: float
    total_max_loss: float
    risk_percent: float
    risk_amount: float
    potential_credit: float
    total_credit: float
    risk_reward_ratio: float
    kelly_percent: Optional[float] = None
    recommended_size: Optional[float] = None


@dataclass
class RiskMetrics:
    """Risk metrics for a trading strategy."""
    win_rate: float
    avg_win: float
    avg_loss: float
    profit_factor: float
    kelly_percent: float
    kelly_half: float
    kelly_quarter: float
    expected_value: float


class PositionSizingCalculator:
    """
    Calculates optimal position sizes for Iron Condor trades.
    
    Supports:
    - Fixed percentage risk per trade
    - Kelly criterion optimization
    - Risk/reward ratio analysis
    - Multi-contract sizing
    """
    
    STOXX50_MULTIPLIER = 10  # €10 per point per contract
    
    def __init__(self, account_balance: float = 10000.0):
        """
        Initialize calculator.
        
        Args:
            account_balance: Total account balance in euros
        """
        self.account_balance = account_balance
    
    def calculate_max_loss_per_spread(self, wing_width: int, credit: float) -> float:
        """
        Calculate maximum loss per spread.
        
        For Iron Condor:
        - Max loss = wing_width - credit received
        - If breach, loss is difference between strike and breach point
        
        Args:
            wing_width: Width of wings in points (default 50 for STOXX50)
            credit: Credit received per spread in euros
            
        Returns:
            Maximum loss per spread in euros
        """
        return (wing_width - credit) * self.STOXX50_MULTIPLIER
    
    def calculate_position_size(
        self,
        credit: float,
        wing_width: int = 50,
        risk_percent: float = 1.0,
        max_risk_amount: Optional[float] = None,
        use_kelly: bool = False,
        kelly_fraction: float = 0.5,
        win_rate: float = 0.65,
        avg_win: float = 250.0,
        avg_loss: float = -350.0
    ) -> PositionSize:
        """
        Calculate optimal position size (number of spreads).
        
        Args:
            credit: Credit received per spread in euros
            wing_width: Width of wings in points (default 50)
            risk_percent: Max % of account to risk per trade (default 1%)
            max_risk_amount: Override risk percent with fixed amount
            use_kelly: Use Kelly criterion instead of fixed percentage
            kelly_fraction: Fraction of Kelly to use (0.5 = half-Kelly)
            win_rate: Historical win rate (0-1)
            avg_win: Average winning trade in euros
            avg_loss: Average losing trade in euros
            
        Returns:
            PositionSize dataclass with all calculations
        """
        credit_total = credit * self.STOXX50_MULTIPLIER
        max_loss_per_spread = self.calculate_max_loss_per_spread(wing_width, credit)
        
        if use_kelly:
            kelly = self.calculate_kelly_criterion(win_rate, avg_win, avg_loss)
            risk_amount = self.account_balance * (kelly * kelly_fraction)
            kelly_percent = kelly * 100
        else:
            risk_amount = max_risk_amount or (self.account_balance * risk_percent / 100)
            kelly_percent = None
        
        if max_loss_per_spread <= 0:
            raise ValueError(f"Invalid max loss per spread: {max_loss_per_spread}")
        
        spreads = int(risk_amount // max_loss_per_spread)
        spreads = max(1, spreads)  # Minimum 1 spread
        
        total_max_loss = spreads * max_loss_per_spread
        total_credit = spreads * credit_total
        
        risk_reward = max_loss_per_spread / credit_total if credit_total > 0 else 0
        
        recommended_size = spreads * self.STOXX50_MULTIPLIER * wing_width
        
        return PositionSize(
            spreads=spreads,
            contracts_per_spread=1,
            max_loss_per_spread=max_loss_per_spread,
            total_max_loss=total_max_loss,
            risk_percent=risk_percent if not use_kelly else kelly_percent or 0,
            risk_amount=risk_amount,
            potential_credit=credit_total,
            total_credit=total_credit,
            risk_reward_ratio=risk_reward,
            kelly_percent=kelly_percent,
            recommended_size=recommended_size
        )
    
    def calculate_kelly_criterion(
        self,
        win_rate: float,
        avg_win: float,
        avg_loss: float
    ) -> float:
        """
        Calculate Kelly criterion percentage.
        
        Kelly % = W - [(1-W) / R]
        Where:
        - W = Win rate
        - R = Win/Loss ratio (avg_win / |avg_loss|)
        
        Args:
            win_rate: Historical win rate (0-1)
            avg_win: Average winning trade in euros
            avg_loss: Average losing trade in euros (positive value)
            
        Returns:
            Kelly percentage (0-1). Returns 0 if invalid inputs.
        """
        if win_rate <= 0 or win_rate >= 1:
            return 0.0
        
        loss_abs = abs(avg_loss)
        if loss_abs <= 0:
            return 0.0
        
        win_loss_ratio = avg_win / loss_abs
        kelly = win_rate - ((1 - win_rate) / win_loss_ratio)
        
        return max(0.0, min(1.0, kelly))  # Clamp to 0-1
    
    def calculate_risk_metrics(
        self,
        win_rate: float,
        avg_win: float,
        avg_loss: float
    ) -> RiskMetrics:
        """
        Calculate comprehensive risk metrics for a strategy.
        
        Args:
            win_rate: Historical win rate (0-1)
            avg_win: Average winning trade in euros
            avg_loss: Average losing trade in euros
            
        Returns:
            RiskMetrics dataclass
        """
        kelly = self.calculate_kelly_criterion(win_rate, avg_win, avg_loss)
        
        profit_factor = (avg_win * win_rate) / (abs(avg_loss) * (1 - win_rate)) if (1 - win_rate) > 0 else 0
        
        expected_value = (win_rate * avg_win) + ((1 - win_rate) * avg_loss)
        
        return RiskMetrics(
            win_rate=win_rate * 100,
            avg_win=avg_win,
            avg_loss=avg_loss,
            profit_factor=profit_factor,
            kelly_percent=kelly * 100,
            kelly_half=kelly * 50,
            kelly_quarter=kelly * 25,
            expected_value=expected_value
        )
    
    def format_position_summary(self, position: PositionSize) -> str:
        """
        Format position size as a readable summary.
        
        Args:
            position: PositionSize dataclass
            
        Returns:
            Formatted string summary
        """
        lines = [
            "=" * 50,
            "POSITION SIZE CALCULATION",
            "=" * 50,
            f"Suggested Size:      {position.spreads} spreads ({position.contracts_per_spread} contract(s) each)",
            f"Max Loss/Spread:     €{position.max_loss_per_spread:.2f}",
            f"Total Max Loss:      €{position.total_max_loss:.2f}",
            f"Total Credit:        €{position.total_credit:.2f}",
            f"Risk/Reward Ratio:   1:{position.risk_reward_ratio:.2f}",
        ]
        
        if position.kelly_percent is not None:
            lines.extend([
                f"Kelly Criterion:     {position.kelly_percent:.2f}%",
                f"Recommended Size:    {position.recommended_size:.0f} contracts",
            ])
        
        lines.extend([
            "=" * 50,
            f"Note: Max risk is €{position.risk_amount:.2f} ({position.risk_percent:.2f}% of account)",
            f"Account Balance:     €{self.account_balance:,.2f}",
        ])
        
        return "\n".join(lines)
    
    def calculate_from_portfolio(
        self,
        portfolio_data: Dict[str, Any],
        wing_width: int = 50,
        risk_percent: float = 1.0
    ) -> Dict[str, PositionSize]:
        """
        Calculate position sizes for both portfolio strategies.
        
        Args:
            portfolio_data: Portfolio data from portfolio.py
            wing_width: Width of wings in points
            risk_percent: Max % of account to risk per trade
            
        Returns:
            Dict with 'always_trade' and 'filtered' position sizes
        """
        results = {}
        
        for name, portfolio in portfolio_data.get('portfolios', {}).items():
            trade_count = portfolio.get('trade_count', 0)
            
            if trade_count < 10:
                results[name] = None
                continue
            
            total_pnl = portfolio.get('total_pnl', 0)
            win_count = portfolio.get('win_count', 0)
            win_rate = win_count / trade_count if trade_count > 0 else 0.5
            
            avg_trade = total_pnl / trade_count
            
            if avg_trade >= 0:
                avg_win = abs(avg_trade) * 2
                avg_loss = -abs(avg_trade)
            else:
                avg_win = abs(avg_trade)
                avg_loss = abs(avg_trade) * 2
            
            try:
                position = self.calculate_position_size(
                    credit=2.50,
                    wing_width=wing_width,
                    risk_percent=risk_percent,
                    win_rate=win_rate,
                    avg_win=avg_win,
                    avg_loss=avg_loss
                )
                results[name] = position
            except (ValueError, ZeroDivisionError):
                results[name] = None
        
        return results


def calculate_position_size_cli(
    account_balance: float = 10000.0,
    credit: float = 2.50,
    wing_width: int = 50,
    risk_percent: float = 1.0,
    use_kelly: bool = False
):
    """
    CLI interface for position sizing calculator.
    """
    calculator = PositionSizingCalculator(account_balance)
    
    try:
        position = calculator.calculate_position_size(
            credit=credit,
            wing_width=wing_width,
            risk_percent=risk_percent,
            use_kelly=use_kelly
        )
        
        print(calculator.format_position_summary(position))
        
        return position
        
    except ValueError as e:
        print(f"Error: {e}")
        return None


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Position Sizing Calculator for STOXX50 Iron Condor"
    )
    
    parser.add_argument("--balance", type=float, default=10000,
                        help="Account balance in euros (default: 10000)")
    parser.add_argument("--credit", type=float, default=2.50,
                        help="Credit received per spread (default: 2.50)")
    parser.add_argument("--wing-width", type=int, default=50,
                        help="Wing width in points (default: 50)")
    parser.add_argument("--risk", type=float, default=1.0,
                        help="Max risk percent per trade (default: 1.0)")
    parser.add_argument("--kelly", action="store_true",
                        help="Use Kelly criterion instead of fixed percentage")
    
    args = parser.parse_args()
    
    calculate_position_size_cli(
        account_balance=args.balance,
        credit=args.credit,
        wing_width=args.wing_width,
        risk_percent=args.risk,
        use_kelly=args.kelly
    )
