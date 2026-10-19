# Supabase Setup Guide for Loki Trading Platform

## Quick Setup

### 1. Get Your Supabase Credentials

1. Go to your Supabase project: https://supabase.com/dashboard/project/vwtmfsrcqyteviyniiqj
2. Navigate to **Settings → API**
3. Copy the following:
   - **Project URL**: `https://vwtmfsrcqyteviyniiqj.supabase.co`
   - **service_role** key (bypasses RLS, required for server-side operations)

### 2. Set Up the Database Schema

1. In Supabase dashboard, go to **SQL Editor**
2. Copy the contents of `supabase_schema.sql`
3. Paste and click **RUN**

This will create the following tables:
- `loki_trades` - Trade history
- `loki_signals` - Trading signals
- `loki_equity_snapshots` - Equity/cash snapshots
- `loki_regime_events` - Market regime changes
- `loki_training_reports` - AI training reports
- `loki_events` - System events

### 3. Configure Environment Variables

Create or edit your `.env` file in the project root:

```bash
# Supabase Configuration
SUPABASE_URL=https://vwtmfsrcqyteviyniiqj.supabase.co
SUPABASE_SERVICE_KEY=your_service_role_key_here
SUPABASE_ANON_KEY=your_anon_key_here
```

**⚠️ Security Note:** Never commit the `.env` file to git. The service_role key should only be used server-side.

### 4. Install Dependencies

```bash
pip install supabase python-dotenv
```

Or update requirements.txt:
```bash
pip install -r requirements.txt
```

### 5. Test the Connection

Run the test script:

```bash
python supabase_manager.py
```

This will:
- Test the database connection
- Insert a sample trade
- Retrieve trades
- Calculate performance summary

## Usage

### In Your Code

```python
from supabase_manager import LokiSupabaseManager
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()

# Create manager
db = LokiSupabaseManager()

# Insert a trade
trade_data = {
    'symbol': 'BTC/USD',
    'side': 'long',
    'qty': 0.1,
    'entry_price': 50000.0,
    'exit_price': 51000.0,
    'pnl': 100.0,
    'pnl_pct': 0.02,
    'exit_reason': 'target',
    'mode': 'paper',
    'source': 'engine',
    'equity_at_trade': 25000.0
}
db.insert_trade(trade_data)

# Get trades
trades = db.get_trades(symbol='BTC/USD', limit=10)

# Get performance summary
summary = db.get_performance_summary()
print(f"Win Rate: {summary['win_rate']:.2%}")
```

## Available Operations

### Trades
- `insert_trade(trade_data)` - Insert a trade record
- `get_trades(symbol=None, limit=100, mode=None)` - Retrieve trades

### Signals
- `insert_signal(signal_data)` - Insert a trading signal
- `get_signals(symbol=None, limit=100)` - Retrieve signals

### Equity
- `insert_equity_snapshot(equity_data)` - Insert equity snapshot
- `get_equity_history(limit=1000)` - Retrieve equity history

### Regimes
- `insert_regime_event(regime_data)` - Insert regime change
- `get_regime_history(symbol=None, limit=100)` - Retrieve regime history

### Training
- `insert_training_report(report_data)` - Insert training report
- `get_training_reports(limit=50)` - Retrieve training reports

### Events
- `insert_event(event_data)` - Insert system event
- `get_events(kind=None, limit=100)` - Retrieve events

### Analytics
- `get_performance_summary()` - Calculate performance metrics

## MCP Server Configuration

To use the Supabase MCP server (if you have MCP configured in your environment), add this to your MCP client configuration:

```json
{
  "mcpServers": {
    "supabase": {
      "command": "npx",
      "args": [
        "-y",
        "@supabase/mcp-server",
        "project_ref=vwtmfsrcqyteviyniiqj",
        "features=docs,account,database,debugging,development,functions,branching"
      ]
    }
  }
}
```

## Troubleshooting

### Connection Failed
- Verify your SUPABASE_URL and SUPABASE_SERVICE_KEY are correct
- Check that the SQL schema has been run in Supabase
- Ensure your network allows connections to supabase.co

### Insert Failed
- Check that the required fields are provided
- Verify data types match the schema
- Check Row Level Security (RLS) policies in Supabase

### RLS Issues
- The service_role key bypasses RLS
- If using anon_key, ensure RLS policies allow inserts
- For server-side operations, always use service_role

## Security Best Practices

1. **Never commit** `.env` file with real keys
2. **Use service_role** only on server-side
3. **Use anon_key** for client-side operations
4. **Enable RLS** in Supabase for production
5. **Rotate keys** periodically
6. **Monitor** database access logs

## Next Steps

1. ✅ Set up environment variables
2. ✅ Run SQL schema in Supabase
3. ✅ Test connection with `python supabase_manager.py`
4. ✅ Integrate into your trading bot
5. ✅ Monitor data in Supabase dashboard

For more information, visit:
- Supabase Documentation: https://supabase.com/docs
- Your Project Dashboard: https://supabase.com/dashboard/project/vwtmfsrcqyteviyniiqj
