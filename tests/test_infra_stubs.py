"""
Stub implementations of infra functions for testing.
"""
import os
import json
import tempfile

# Create a temporary state directory for tests
TEMP_STATE_DIR = tempfile.mkdtemp()

def state_path(filename: str) -> str:
    """Return path to state file in temp directory."""
    return os.path.join(TEMP_STATE_DIR, filename)

def read_json(path: str, default=None):
    """Read JSON file or return default."""
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return default

def atomic_write_json(path: str, payload) -> None:
    """Write JSON atomically."""
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    with open(path, "w") as f:
        json.dump(payload, f, default=str, indent=2)

def load_daily_pnl(date_str: str) -> float:
    """Load daily P&L from temp storage."""
    data = read_json(state_path(f"daily_pnl_{date_str}.json"), default={})
    return data.get('pnl', 0.0)

def save_daily_pnl(date_str: str, pnl: float) -> None:
    """Save daily P&L to temp storage."""
    atomic_write_json(state_path(f"daily_pnl_{date_str}.json"), {'pnl': pnl, 'date': date_str})

def load_weekly_pnl(week_str: str) -> float:
    """Load weekly P&L from temp storage."""
    data = read_json(state_path(f"weekly_pnl_{week_str}.json"), default={})
    return data.get('pnl', 0.0)

def save_weekly_pnl(week_str: str, pnl: float) -> None:
    """Save weekly P&L to temp storage."""
    atomic_write_json(state_path(f"weekly_pnl_{week_str}.json"), {'pnl': pnl, 'week': week_str})

def load_week_trade_days(week_str: str) -> list:
    """Load trade days for a week."""
    data = read_json(state_path(f"week_days_{week_str}.json"), default={})
    return data.get('days', [])

def add_week_trade_day(week_str: str, date_str: str) -> None:
    """Add a trade day to the week."""
    days = load_week_trade_days(week_str)
    if date_str not in days:
        days.append(date_str)
        atomic_write_json(state_path(f"week_days_{week_str}.json"), {'days': days, 'week': week_str})