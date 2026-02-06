# Backtest Optimizer Plan

## Overview

A parameter optimization tool that systematically tests combinations of strategy parameters to find optimal settings for the STOXX50 0DTE Iron Condor strategy. Uses grid search with optional walk-forward validation.

---

## Goals

1. **Find optimal parameters** - Test combinations to maximize risk-adjusted returns
2. **Avoid overfitting** - Use walk-forward validation to test out-of-sample performance
3. **Generate actionable output** - Report best parameters with confidence metrics
4. **Integrate with existing codebase** - Reuse `backtest.py` logic, respect config structure

---

## Parameters to Optimize

| Parameter | Config Path | Current Default | Search Range | Step |
|-----------|-------------|-----------------|--------------|------|
| OTM Percent | `strikes.otm_percent` | 1.0% | 0.5% - 2.0% | 0.25% |
| Wing Width | `strikes.wing_width` | 50 pts | 25 - 100 pts | 25 pts |
| Intraday Change Max | `rules.intraday_change_max` | 1.0% | 0.5% - 2.0% | 0.25% |
| Credit | (trade param) | €2.50 | €1.50 - €4.00 | €0.50 |

**Fixed parameters** (not optimized):
- VSTOXX threshold: 25 (rule 1)
- Economic calendar: Always check (rule 3)

---

## Architecture

### New File: `optimize.py`

```
optimize.py
├── ParameterGrid          # Generate parameter combinations
├── BacktestRunner         # Run single backtest with params
├── WalkForwardValidator   # Split data into train/test windows
├── ResultsAnalyzer        # Compute metrics, rank results
├── ReportGenerator        # Output reports (terminal, CSV, JSON)
└── main()                 # CLI interface
```

### Module Structure

```python
# optimize.py

from dataclasses import dataclass
from typing import List, Dict, Tuple
import itertools

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
    is_train: bool  # True = in-sample, False = out-of-sample

class ParameterGrid:
    """Generate all parameter combinations."""

    def __init__(self, ranges: Dict[str, List]):
        self.ranges = ranges

    def generate(self) -> List[ParameterSet]:
        keys = list(self.ranges.keys())
        values = list(self.ranges.values())
        combinations = list(itertools.product(*values))
        return [ParameterSet(**dict(zip(keys, combo))) for combo in combinations]

class BacktestRunner:
    """Run backtest with specific parameters."""

    def run(self, params: ParameterSet, start_date: str, end_date: str) -> BacktestResult:
        # Modify evaluate_day() to use params.intraday_change_max
        # Modify simulate_iron_condor() to use params
        # Return metrics
        pass

class WalkForwardValidator:
    """Split data into rolling train/test windows."""

    def __init__(self, train_months: int = 6, test_months: int = 2):
        self.train_months = train_months
        self.test_months = test_months

    def get_windows(self, start_date: str, end_date: str) -> List[Tuple[str, str, str, str]]:
        """Return list of (train_start, train_end, test_start, test_end) tuples."""
        pass
```

---

## Walk-Forward Validation

To prevent overfitting, use rolling train/test windows:

```
|------- Full Period 2024-01-01 to 2024-12-31 -------|

Window 1:
|-- Train: Jan-Jun --|-- Test: Jul-Aug --|

Window 2:
    |-- Train: Mar-Aug --|-- Test: Sep-Oct --|

Window 3:
        |-- Train: May-Oct --|-- Test: Nov-Dec --|
```

**Process:**
1. For each parameter combination:
   - Run backtest on each train window → in-sample results
   - Run backtest on corresponding test window → out-of-sample results
2. Rank by out-of-sample performance (not in-sample!)
3. Report both metrics for comparison

---

## Metrics

### Primary Ranking Metric: Sortino Ratio
- Focuses on downside risk (only penalizes negative returns)
- Better than Sharpe for asymmetric P&L (options have capped upside)

### Secondary Metrics
| Metric | Formula | Purpose |
|--------|---------|---------|
| Total P&L | Σ(trade P&L) | Absolute profit |
| Win Rate | wins / trades | Consistency |
| Profit Factor | Σ(wins) / Σ(losses) | Risk/reward |
| Max Drawdown | max peak-to-trough decline | Worst case |
| Sharpe Ratio | mean(returns) / std(returns) | Risk-adjusted |
| Trade Frequency | trades / days | How often we trade |

### Overfitting Detection
- Compare in-sample vs out-of-sample Sortino ratio
- Flag if in-sample >> out-of-sample (likely overfit)
- Compute "robustness score": out-of-sample / in-sample ratio

---

## CLI Interface

```bash
# Basic optimization (uses defaults)
python optimize.py --start 2023-01-01 --end 2024-12-31

# Custom parameter ranges
python optimize.py --start 2023-01-01 --end 2024-12-31 \
    --otm-range 0.5,0.75,1.0,1.25,1.5 \
    --wing-range 25,50,75 \
    --intraday-range 0.75,1.0,1.25

# Quick mode (fewer combinations)
python optimize.py --start 2024-01-01 --end 2024-12-31 --quick

# Walk-forward disabled (faster but higher overfit risk)
python optimize.py --start 2024-01-01 --end 2024-12-31 --no-walkforward

# Export results
python optimize.py --start 2024-01-01 --end 2024-12-31 --output results.csv
```

### Arguments

| Argument | Default | Description |
|----------|---------|-------------|
| `--start` | Required | Start date (YYYY-MM-DD) |
| `--end` | Required | End date (YYYY-MM-DD) |
| `--otm-range` | `0.5,0.75,1.0,1.25,1.5,1.75,2.0` | OTM percent values |
| `--wing-range` | `25,50,75,100` | Wing width values |
| `--intraday-range` | `0.5,0.75,1.0,1.25,1.5,1.75,2.0` | Intraday change max values |
| `--credit-range` | `1.5,2.0,2.5,3.0,3.5,4.0` | Credit values |
| `--train-months` | `6` | Training window size |
| `--test-months` | `2` | Test window size |
| `--no-walkforward` | `False` | Disable walk-forward validation |
| `--quick` | `False` | Use reduced parameter grid |
| `--output` | `None` | Export results to CSV/JSON |
| `--top` | `10` | Show top N results |
| `--workers` | `4` | Parallel workers (multiprocessing) |

---

## Output Format

### Terminal Output

```
================================================================================
  STOXX50 BACKTEST OPTIMIZER
  Period: 2023-01-01 to 2024-12-31
  Parameter combinations: 168
  Walk-forward windows: 3
================================================================================

Running optimization... [████████████████████████] 100%

================================================================================
  TOP 10 PARAMETER SETS (ranked by out-of-sample Sortino)
================================================================================

Rank  OTM%   Wing  Intra%  Credit  |  In-Sample           |  Out-of-Sample
                                    |  P&L     Win%  Sort  |  P&L     Win%  Sort
----------------------------------------------------------------------------------
  1   1.00    50   1.00    €2.50   |  €4,200  72%   1.42  |  €1,850  68%   1.28
  2   0.75    50   0.75    €2.50   |  €3,800  70%   1.35  |  €1,720  66%   1.21
  3   1.25    50   1.00    €3.00   |  €4,500  74%   1.51  |  €1,650  65%   1.18
...

================================================================================
  RECOMMENDED PARAMETERS
================================================================================

Based on out-of-sample performance with robustness check:

  strikes:
    otm_percent: 1.0
    wing_width: 50

  rules:
    intraday_change_max: 1.0

  Suggested credit: €2.50

  Robustness Score: 0.90 (out-of-sample / in-sample)
  Warning: None - parameters appear stable

================================================================================
```

### CSV Export

```csv
rank,otm_percent,wing_width,intraday_max,credit,is_pnl,is_win_rate,is_sortino,oos_pnl,oos_win_rate,oos_sortino,robustness
1,1.00,50,1.00,2.50,4200,0.72,1.42,1850,0.68,1.28,0.90
2,0.75,50,0.75,2.50,3800,0.70,1.35,1720,0.66,1.21,0.90
...
```

---

## Implementation Plan

### Phase 1: Core Infrastructure (Priority)

1. **Create `optimize.py` skeleton**
   - Import existing `backtest.py` functions
   - Define dataclasses for ParameterSet and BacktestResult

2. **Implement ParameterGrid**
   - Generate combinations from ranges
   - Support custom ranges via CLI

3. **Modify backtest logic for parameterization**
   - Create `run_single_backtest(params, start, end)` function
   - Return structured result with all metrics

### Phase 2: Walk-Forward Validation

4. **Implement WalkForwardValidator**
   - Rolling window generation
   - Handle edge cases (insufficient data)

5. **Implement ResultsAnalyzer**
   - Compute Sortino, Sharpe, max drawdown
   - Rank by out-of-sample performance
   - Detect overfitting

### Phase 3: Parallelization & Output

6. **Add multiprocessing**
   - Use `concurrent.futures.ProcessPoolExecutor`
   - Progress bar with `tqdm`

7. **Implement ReportGenerator**
   - Terminal output (colored, formatted)
   - CSV/JSON export

### Phase 4: Polish

8. **CLI interface**
   - argparse with all options
   - Validation and help text

9. **Testing**
   - Unit tests for grid generation
   - Integration test with sample data

10. **Documentation**
    - Usage examples
    - Interpretation guide

---

## Dependencies

**New:**
- `tqdm` - Progress bars (add to requirements.txt)

**Existing:**
- `pandas` - Data manipulation
- `yfinance` - Market data
- `termcolor` - Colored output

---

## Files to Create/Modify

| File | Action | Description |
|------|--------|-------------|
| `optimize.py` | Create | Main optimizer module |
| `backtest.py` | Modify | Extract reusable functions, add parameterization |
| `requirements.txt` | Modify | Add `tqdm` |
| `config.yaml.example` | Modify | Document optimizer settings (optional) |

---

## Risk Considerations

1. **Overfitting** - Walk-forward validation mitigates but doesn't eliminate
2. **Data snooping** - Running optimizer multiple times on same data introduces bias
3. **Regime changes** - Past optimal params may not work in future market conditions
4. **Execution reality** - Backtest assumes fills at theoretical prices

**Recommendations in output:**
- Always note that past performance doesn't guarantee future results
- Suggest using conservative parameters (middle of optimal range)
- Recommend re-running optimizer quarterly with new data

---

## Example Usage

```bash
# Standard 2-year optimization
python optimize.py -s 2023-01-01 -e 2024-12-31

# Quick test (fewer combinations)
python optimize.py -s 2024-01-01 -e 2024-12-31 --quick

# Export for analysis
python optimize.py -s 2023-01-01 -e 2024-12-31 --output optimization_results.csv

# Custom ranges for specific testing
python optimize.py -s 2024-01-01 -e 2024-12-31 \
    --otm-range 0.75,1.0,1.25 \
    --wing-range 50 \
    --intraday-range 0.75,1.0,1.25
```

---

## Timeline Estimate

| Phase | Effort |
|-------|--------|
| Phase 1: Core | Medium |
| Phase 2: Walk-Forward | Medium |
| Phase 3: Parallel & Output | Light |
| Phase 4: Polish | Light |

---

## Future Enhancements (Not in Scope)

- Bayesian optimization (smarter than grid search)
- Monte Carlo simulation for confidence intervals
- Genetic algorithms for parameter search
- Integration with dashboard visualization
- Automatic parameter scheduling (reoptimize on schedule)
