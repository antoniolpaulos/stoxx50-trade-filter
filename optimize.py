#!/usr/bin/env python3
"""
STOXX50 Backtest Optimizer
Tests parameter combinations to find optimal strategy settings.
"""

import argparse
import itertools
import json
import csv
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Optional
from concurrent.futures import ProcessPoolExecutor
import yfinance as yf
import pandas as pd
from termcolor import colored
from tqdm import tqdm

from trade_filter import calculate_strikes


@dataclass
class ParameterSet:
    otm_percent: float
    wing_width: int
    intraday_change_max: float
    credit: float


@dataclass
class BacktestResult:
    params: ParameterSet
    total_pnl: float
    trades: int
    win_rate: float
    profit_factor: float
    max_drawdown: float
    sharpe_ratio: float
    sortino_ratio: float
    trades_list: List[Dict] = field(default_factory=list)
    is_train: bool = True


def get_historical_data(start_date: str, end_date: str) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Fetch historical VIX and Euro Stoxx 50 data."""
    buffer_start = (datetime.strptime(start_date, '%Y-%m-%d') - timedelta(days=5)).strftime('%Y-%m-%d')
    buffer_end = (datetime.strptime(end_date, '%Y-%m-%d') + timedelta(days=5)).strftime('%Y-%m-%d')

    vix = yf.Ticker("^VIX")
    stoxx = yf.Ticker("^STOXX50E")

    vix_data = vix.history(start=buffer_start, end=buffer_end)
    stoxx_data = stoxx.history(start=buffer_start, end=buffer_end)

    return vix_data, stoxx_data


def evaluate_day(vix_close: Optional[float], stoxx_open: float, stoxx_close: float,
                 intraday_change_max: float = 1.0) -> Tuple[bool, str, float, bool]:
    """Evaluate if we would trade on this day with configurable threshold."""
    intraday_change = ((stoxx_close - stoxx_open) / stoxx_open) * 100
    vix_warning = vix_close is not None and vix_close > 22

    if abs(intraday_change) > intraday_change_max:
        return False, f"Trend too strong ({intraday_change:+.2f}%)", intraday_change, vix_warning

    return True, "Conditions met", intraday_change, vix_warning


def simulate_iron_condor(stoxx_close: float, put_strike: float, call_strike: float,
                         wing_width: float, credit: float) -> float:
    """Simulate Iron Condor P&L."""
    multiplier = 10

    if stoxx_close <= put_strike:
        intrinsic = put_strike - stoxx_close
        loss = min(intrinsic, wing_width) - credit
        return -loss * multiplier
    elif stoxx_close >= call_strike:
        intrinsic = stoxx_close - call_strike
        loss = min(intrinsic, wing_width) - credit
        return -loss * multiplier
    else:
        return credit * multiplier


def run_single_backtest(params: ParameterSet, start_date: str, end_date: str,
                        vix_data: pd.DataFrame, stoxx_data: pd.DataFrame,
                        verbose: bool = False) -> BacktestResult:
    """Run backtest with specific parameters."""
    start_dt = datetime.strptime(start_date, '%Y-%m-%d')
    end_dt = datetime.strptime(end_date, '%Y-%m-%d')

    total_pnl = 0
    trades_taken = 0
    wins = 0
    losses = 0
    trades_list = []
    peak = 0
    max_drawdown = 0

    for date in stoxx_data.index:
        date_only = date.replace(tzinfo=None)
        if date_only < start_dt or date_only > end_dt:
            continue

        try:
            stoxx_row = stoxx_data.loc[date]
        except KeyError:
            continue

        try:
            vix_row = vix_data.loc[date]
            vix_close = vix_row['Close']
        except KeyError:
            vix_close = None

        stoxx_open = stoxx_row['Open']
        stoxx_high = stoxx_row['High']
        stoxx_low = stoxx_row['Low']
        stoxx_close = stoxx_row['Close']

        stoxx_entry = stoxx_open + (((stoxx_high + stoxx_low) / 2) - stoxx_open) * 0.3

        should_trade, _, intraday_change, _ = evaluate_day(
            vix_close, stoxx_open, stoxx_close, params.intraday_change_max
        )

        if should_trade:
            trades_taken += 1
            call_strike, put_strike = calculate_strikes(stoxx_entry, params.otm_percent)
            pnl = simulate_iron_condor(stoxx_close, put_strike, call_strike,
                                        params.wing_width, params.credit)
            total_pnl += pnl

            if pnl > 0:
                wins += 1
            else:
                losses += 1

            trades_list.append({
                'date': date.strftime('%Y-%m-%d'),
                'pnl': pnl,
                'stoxx_close': stoxx_close
            })

            peak = max(peak, total_pnl)
            drawdown = peak - total_pnl
            max_drawdown = max(max_drawdown, drawdown)

    win_rate = (wins / trades_taken * 100) if trades_taken > 0 else 0
    avg_pnl = total_pnl / trades_taken if trades_taken > 0 else 0

    pf = 0
    if losses != 0 and sum(t['pnl'] for t in trades_list if t['pnl'] < 0) != 0:
        pf = abs(sum(t['pnl'] for t in trades_list if t['pnl'] > 0) /
                 sum(t['pnl'] for t in trades_list if t['pnl'] < 0))

    returns = [t['pnl'] for t in trades_list]
    sharpe = 0
    sortino = 0
    if len(returns) > 1:
        mean_ret = sum(returns) / len(returns)
        std_ret = (sum((r - mean_ret) ** 2 for r in returns) / len(returns)) ** 0.5
        sharpe = mean_ret / std_ret if std_ret > 0 else 0

        downside_returns = [r for r in returns if r < 0]
        if downside_returns:
            downside_std = (sum((r - mean_ret) ** 2 for r in downside_returns) / len(downside_returns)) ** 0.5
            sortino = mean_ret / downside_std if downside_std > 0 else 0
        else:
            sortino = float('inf') if mean_ret > 0 else 0

    return BacktestResult(
        params=params,
        total_pnl=total_pnl,
        trades=trades_taken,
        win_rate=win_rate,
        profit_factor=pf,
        max_drawdown=max_drawdown,
        sharpe_ratio=sharpe,
        sortino_ratio=sortino,
        trades_list=trades_list
    )


class ParameterGrid:
    """Generate parameter combinations."""

    def __init__(self, otm_range: List[float], wing_range: List[int],
                 intraday_range: List[float], credit_range: List[float]):
        self.otm_range = otm_range
        self.wing_range = wing_range
        self.intraday_range = intraday_range
        self.credit_range = credit_range

    def generate(self) -> List[ParameterSet]:
        combinations = list(itertools.product(
            self.otm_range, self.wing_range, self.intraday_range, self.credit_range
        ))
        return [ParameterSet(*combo) for combo in combinations]

    def count(self) -> int:
        return len(self.otm_range) * len(self.wing_range) * len(self.intraday_range) * len(self.credit_range)


class WalkForwardValidator:
    """Split data into rolling train/test windows."""

    def __init__(self, train_months: int = 6, test_months: int = 2):
        self.train_months = train_months
        self.test_months = test_months

    def get_windows(self, start_date: str, end_date: str,
                    vix_data: pd.DataFrame, stoxx_data: pd.DataFrame) -> List[Tuple[str, str, str, str]]:
        """Return list of (train_start, train_end, test_start, test_end) tuples."""
        start_dt = datetime.strptime(start_date, '%Y-%m-%d')
        end_dt = datetime.strptime(end_date, '%Y-%m-%d')

        dates = sorted([d.replace(tzinfo=None) for d in stoxx_data.index])
        if not dates:
            return []

        available_start = max(start_dt, dates[0])
        available_end = min(end_dt, dates[-1])

        windows = []
        current_train_start = available_start

        while True:
            train_end = current_train_start + timedelta(days=self.train_months * 30)
            test_start = train_end + timedelta(days=1)
            test_end = test_start + timedelta(days=self.test_months * 30)

            if test_end > available_end:
                break

            train_end_str = train_end.strftime('%Y-%m-%d')
            test_start_str = test_start.strftime('%Y-%m-%d')
            test_end_str = min(test_end, available_end).strftime('%Y-%m-%d')

            if train_end_str <= end_date and test_start_str <= end_date:
                windows.append((current_train_start.strftime('%Y-%m-%d'), train_end_str,
                                 test_start_str, test_end_str))

            current_train_start = test_start - timedelta(days=self.train_months * 15)

        return windows


def run_optimization(params: ParameterSet, windows: List[Tuple[str, str, str, str]],
                     vix_data: pd.DataFrame, stoxx_data: pd.DataFrame,
                     use_walkforward: bool) -> Tuple[BacktestResult, Optional[BacktestResult]]:
    """Run optimization for a single parameter set."""
    if not use_walkforward or len(windows) == 0:
        full_start = windows[0][0] if windows else '2024-01-01'
        full_end = windows[-1][3] if windows else '2024-12-31'
        result = run_single_backtest(params, full_start, full_end, vix_data, stoxx_data)
        return result, None

    train_results = []
    test_results = []

    for train_start, train_end, test_start, test_end in windows:
        train_result = run_single_backtest(params, train_start, train_end, vix_data, stoxx_data)
        test_result = run_single_backtest(params, test_start, test_end, vix_data, stoxx_data)
        train_results.append(train_result)
        test_results.append(test_result)

    combined_train = combine_results(train_results)
    combined_test = combine_results(test_results)
    combined_test.is_train = False

    return combined_train, combined_test


def combine_results(results: List[BacktestResult]) -> BacktestResult:
    """Combine results from multiple windows."""
    all_trades = []
    total_pnl = sum(r.total_pnl for r in results)
    total_trades = sum(r.trades for r in results)
    wins = sum(1 for r in results for t in r.trades_list if t['pnl'] > 0)
    losses = sum(1 for r in results for t in r.trades_list if t['pnl'] < 0)

    for r in results:
        all_trades.extend(r.trades_list)

    peak = 0
    max_drawdown = 0
    cumulative = 0
    for trade in sorted(all_trades, key=lambda x: x['date']):
        cumulative += trade['pnl']
        peak = max(peak, cumulative)
        max_drawdown = max(max_drawdown, peak - cumulative)

    win_rate = (wins / total_trades * 100) if total_trades > 0 else 0

    pf = 0
    wins_sum = sum(t['pnl'] for t in all_trades if t['pnl'] > 0)
    losses_sum = abs(sum(t['pnl'] for t in all_trades if t['pnl'] < 0))
    if losses_sum > 0:
        pf = wins_sum / losses_sum

    returns = [t['pnl'] for t in all_trades]
    sharpe = 0
    sortino = 0
    if len(returns) > 1:
        mean_ret = sum(returns) / len(returns)
        std_ret = (sum((r - mean_ret) ** 2 for r in returns) / len(returns)) ** 0.5
        sharpe = mean_ret / std_ret if std_ret > 0 else 0

        downside_returns = [r for r in returns if r < 0]
        if downside_returns:
            downside_std = (sum((r - mean_ret) ** 2 for r in downside_returns) / len(downside_returns)) ** 0.5
            sortino = mean_ret / downside_std if downside_std > 0 else 0

    return BacktestResult(
        params=results[0].params if results else ParameterSet(1.0, 50, 1.0, 2.5),
        total_pnl=total_pnl,
        trades=total_trades,
        win_rate=win_rate,
        profit_factor=pf,
        max_drawdown=max_drawdown,
        sharpe_ratio=sharpe,
        sortino_ratio=sortino,
        trades_list=all_trades
    )


class ResultsAnalyzer:
    """Analyze and rank optimization results."""

    def __init__(self, results: List[Tuple[BacktestResult, Optional[BacktestResult]]]):
        self.results = results

    def rank(self) -> List[Dict]:
        """Rank results by out-of-sample Sortino ratio."""
        ranked = []
        for train_res, test_res in self.results:
            if test_res:
                robustness = test_res.sortino_ratio / train_res.sortino_ratio if train_res.sortino_ratio > 0 else 0
                ranked.append({
                    'params': train_res.params,
                    'is_train': train_res,
                    'is_test': test_res,
                    'is_pnl': test_res.total_pnl,
                    'is_trades': test_res.trades,
                    'is_win_rate': test_res.win_rate,
                    'is_profit_factor': test_res.profit_factor,
                    'is_sharpe': test_res.sharpe_ratio,
                    'is_sortino': test_res.sortino_ratio,
                    'oos_pnl': test_res.total_pnl,
                    'oos_trades': test_res.trades,
                    'oos_win_rate': test_res.win_rate,
                    'oos_profit_factor': test_res.profit_factor,
                    'oos_sharpe': test_res.sharpe_ratio,
                    'oos_sortino': test_res.sortino_ratio,
                    'robustness': robustness
                })
            else:
                ranked.append({
                    'params': train_res.params,
                    'is_train': train_res,
                    'is_test': None,
                    'is_pnl': train_res.total_pnl,
                    'is_trades': train_res.trades,
                    'is_win_rate': train_res.win_rate,
                    'is_profit_factor': train_res.profit_factor,
                    'is_sharpe': train_res.sharpe_ratio,
                    'is_sortino': train_res.sortino_ratio,
                    'oos_pnl': train_res.total_pnl,
                    'oos_trades': train_res.trades,
                    'oos_win_rate': train_res.win_rate,
                    'oos_profit_factor': train_res.profit_factor,
                    'oos_sharpe': train_res.sharpe_ratio,
                    'oos_sortino': train_res.sortino_ratio,
                    'robustness': 1.0
                })

        ranked.sort(key=lambda x: x['oos_sortino'], reverse=True)
        for i, r in enumerate(ranked):
            r['rank'] = i + 1

        return ranked


def generate_report(ranked_results: List[Dict], start_date: str, end_date: str,
                    total_combinations: int, num_windows: int, use_walkforward: bool) -> str:
    """Generate terminal report."""
    lines = []

    lines.append("=" * 90)
    lines.append(colored("  STOXX50 BACKTEST OPTIMIZER", "cyan", attrs=["bold"]))
    lines.append(colored(f"  Period: {start_date} to {end_date}", "cyan"))
    lines.append(colored(f"  Parameter combinations: {total_combinations}", "cyan"))
    if use_walkforward:
        lines.append(colored(f"  Walk-forward windows: {num_windows}", "cyan"))
    lines.append("=" * 90)
    lines.append("")

    lines.append(colored("  TOP 10 PARAMETER SETS (ranked by out-of-sample Sortino)", "yellow", attrs=["bold"]))
    lines.append("")

    header = f"  {'Rank':<5} {'OTM%':<6} {'Wing':<5} {'Intra%':<7} {'Credit':<7} |"
    header += f"  {'In-Sample':^28} |  {'Out-of-Sample':^28}"
    lines.append(header)
    header2 = f"  {'-'*4} {'-'*5} {'-'*4} {'-'*6} {'-'*6} |"
    header2 += f"  {'P&L':>8} {'Win%':>7} {'Sort':>7} |"
    header2 += f"  {'P&L':>8} {'Win%':>7} {'Sort':>7}"
    lines.append(header2)
    lines.append("  " + "-" * 86)

    for r in ranked_results[:10]:
        params = r['params']
        line = f"  {r['rank']:<5} {params.otm_percent:<6.2f} {params.wing_width:<5} "
        line += f"{params.intraday_change_max:<7.2f} {params.credit:<7.2f} |"
        line += f"  €{r['is_pnl']:>7,.0f} {r['is_win_rate']:>6.1f}% {r['is_sortino']:>7.2f} |"
        line += f"  €{r['oos_pnl']:>7,.0f} {r['oos_win_rate']:>6.1f}% {r['oos_sortino']:>7.2f}"
        lines.append(line)

    lines.append("")
    lines.append("=" * 90)
    lines.append(colored("  RECOMMENDED PARAMETERS", "cyan", attrs=["bold"]))
    lines.append("")

    if ranked_results:
        best = ranked_results[0]
        params = best['params']
        lines.append(f"  Based on out-of-sample performance with robustness check:")
        lines.append("")
        lines.append(f"    strikes:")
        lines.append(f"      otm_percent: {params.otm_percent}")
        lines.append(f"      wing_width: {params.wing_width}")
        lines.append("")
        lines.append(f"    rules:")
        lines.append(f"      intraday_change_max: {params.intraday_change_max}")
        lines.append("")
        lines.append(f"    Suggested credit: €{params.credit}")
        lines.append("")

        robustness = best['robustness']
        if robustness >= 0.8:
            robust_color = "green"
            msg = "Parameters appear stable"
        elif robustness >= 0.5:
            robust_color = "yellow"
            msg = "Moderate overfitting detected"
        else:
            robust_color = "red"
            msg = "Warning: Significant overfitting risk"

        lines.append(f"    Robustness Score: {colored(f'{robustness:.2f}', robust_color)}")
        lines.append(f"    {colored(msg, robust_color)}")

    lines.append("")
    lines.append("=" * 90)

    return "\n".join(lines)


def export_csv(results: List[Dict], filename: str):
    """Export results to CSV."""
    with open(filename, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([
            'rank', 'otm_percent', 'wing_width', 'intraday_max', 'credit',
            'is_pnl', 'is_win_rate', 'is_sharpe', 'is_sortino',
            'oos_pnl', 'oos_win_rate', 'oos_sharpe', 'oos_sortino',
            'robustness'
        ])
        for r in results:
            writer.writerow([
                r['rank'], r['params'].otm_percent, r['params'].wing_width,
                r['params'].intraday_change_max, r['params'].credit,
                r['is_pnl'], r['is_win_rate'], r['is_sharpe'], r['is_sortino'],
                r['oos_pnl'], r['oos_win_rate'], r['oos_sharpe'], r['oos_sortino'],
                r['robustness']
            ])


def export_json(results: List[Dict], filename: str):
    """Export results to JSON."""
    export_data = []
    for r in results:
        export_data.append({
            'rank': r['rank'],
            'params': {
                'otm_percent': r['params'].otm_percent,
                'wing_width': r['params'].wing_width,
                'intraday_change_max': r['params'].intraday_change_max,
                'credit': r['params'].credit
            },
            'in_sample': {
                'pnl': r['is_pnl'],
                'win_rate': r['is_win_rate'],
                'sharpe_ratio': r['is_sharpe'],
                'sortino_ratio': r['is_sortino']
            },
            'out_of_sample': {
                'pnl': r['oos_pnl'],
                'win_rate': r['oos_win_rate'],
                'sharpe_ratio': r['oos_sharpe'],
                'sortino_ratio': r['oos_sortino']
            },
            'robustness_score': r['robustness']
        })

    with open(filename, 'w') as f:
        json.dump(export_data, f, indent=2)


def main():
    parser = argparse.ArgumentParser(
        description='Optimize STOXX50 Iron Condor parameters',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python optimize.py -s 2023-01-01 -e 2024-12-31
  python optimize.py -s 2024-01-01 -e 2024-12-31 --quick
  python optimize.py -s 2023-01-01 -e 2024-12-31 --output results.csv
  python optimize.py -s 2023-01-01 -e 2024-12-31 --otm-range 0.5,0.75,1.0 --wing-range 25,50
        """
    )

    parser.add_argument('--start', '-s', required=True, help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end', '-e', required=True, help='End date (YYYY-MM-DD)')
    parser.add_argument('--otm-range', default='0.5,0.75,1.0,1.25,1.5,1.75,2.0',
                       help='OTM percent values (comma-separated)')
    parser.add_argument('--wing-range', default='25,50,75,100',
                       help='Wing width values (comma-separated)')
    parser.add_argument('--intraday-range', default='0.5,0.75,1.0,1.25,1.5,1.75,2.0',
                       help='Intraday change max values (comma-separated)')
    parser.add_argument('--credit-range', default='1.5,2.0,2.5,3.0,3.5,4.0',
                       help='Credit values (comma-separated)')
    parser.add_argument('--train-months', type=int, default=6, help='Training window months')
    parser.add_argument('--test-months', type=int, default=2, help='Test window months')
    parser.add_argument('--no-walkforward', action='store_true', help='Disable walk-forward validation')
    parser.add_argument('--quick', action='store_true', help='Reduced parameter grid')
    parser.add_argument('--output', '-o', help='Export results to CSV or JSON')
    parser.add_argument('--top', type=int, default=10, help='Number of top results to show')
    parser.add_argument('--workers', type=int, default=1, help='Parallel workers')

    args = parser.parse_args()

    try:
        start_dt = datetime.strptime(args.start, '%Y-%m-%d')
        end_dt = datetime.strptime(args.end, '%Y-%m-%d')
        if start_dt >= end_dt:
            print(colored("Error: Start date must be before end date", "red"))
            return
    except ValueError:
        print(colored("Error: Invalid date format. Use YYYY-MM-DD", "red"))
        return

    if args.quick:
        otm_vals = [0.75, 1.0, 1.25]
        wing_vals = [50]
        intraday_vals = [0.75, 1.0, 1.25]
        credit_vals = [2.0, 2.5, 3.0]
    else:
        otm_vals = [float(x) for x in args.otm_range.split(',')]
        wing_vals = [int(x) for x in args.wing_range.split(',')]
        intraday_vals = [float(x) for x in args.intraday_range.split(',')]
        credit_vals = [float(x) for x in args.credit_range.split(',')]

    grid = ParameterGrid(otm_vals, wing_vals, intraday_vals, credit_vals)
    param_sets = grid.generate()
    total_combinations = len(param_sets)

    print(colored("\nFetching historical data...", "cyan"))
    vix_data, stoxx_data = get_historical_data(args.start, args.end)
    print(f"Got {len(stoxx_data)} trading days of data")

    use_walkforward = not args.no_walkforward
    windows = []
    if use_walkforward:
        validator = WalkForwardValidator(args.train_months, args.test_months)
        windows = validator.get_windows(args.start, args.end, vix_data, stoxx_data)
        if not windows:
            print(colored("Warning: Insufficient data for walk-forward. Running single backtest.", "yellow"))
            use_walkforward = False

    print(colored(f"\nRunning optimization ({total_combinations} combinations)...",
                  "cyan", attrs=["bold"]))

    all_results = []
    if args.workers > 1:
        with ProcessPoolExecutor(max_workers=args.workers) as executor:
            futures = []
            for params in param_sets:
                futures.append(executor.submit(run_optimization, params, windows,
                                               vix_data, stoxx_data, use_walkforward))

            for future in tqdm(futures, total=len(futures), desc="Optimizing"):
                all_results.append(future.result())
    else:
        for params in tqdm(param_sets, desc="Optimizing"):
            all_results.append(run_optimization(params, windows, vix_data, stoxx_data, use_walkforward))

    analyzer = ResultsAnalyzer(all_results)
    ranked_results = analyzer.rank()

    report = generate_report(ranked_results, args.start, args.end,
                             total_combinations, len(windows), use_walkforward)
    print("\n" + report)

    if args.output:
        if args.output.endswith('.csv'):
            export_csv(ranked_results, args.output)
            print(colored(f"\nExported to {args.output}", "green"))
        elif args.output.endswith('.json'):
            export_json(ranked_results, args.output)
            print(colored(f"\nExported to {args.output}", "green"))


if __name__ == "__main__":
    main()
