"""
Test Alpaca Connection
Tests if your Alpaca API keys work correctly
"""
import asyncio
import logging
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    encoding='utf-8'
)

logger = logging.getLogger(__name__)


async def test_alpaca_connection():
    """Test Alpaca API connection."""
    logger.info("Testing Alpaca API connection...")
    
    from core_engine.alpaca_broker import AlpacaBroker, AlpacaConfig, AccountType
    
    # Load config
    config = {}
    env_file = Path('.env.alpaca')
    
    if env_file.exists():
        with open(env_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    config[key.strip()] = value.strip()
    else:
        logger.error(".env.alpaca file not found!")
        return False
    
    # Configure Alpaca
    account_type = AccountType.PAPER if config.get('ALPACA_ACCOUNT_TYPE') == 'paper' else AccountType.LIVE
    base_url = "https://paper-api.alpaca.markets" if account_type == AccountType.PAPER else "https://api.alpaca.markets"
    
    alpaca_config = AlpacaConfig(
        api_key=config.get('ALPACA_API_KEY'),
        api_secret=config.get('ALPACA_API_SECRET'),
        account_type=account_type,
        base_url=base_url
    )
    
    broker = AlpacaBroker(alpaca_config)
    
    # Test connection
    success = await broker.initialize()
    
    if success:
        logger.info("SUCCESS: Alpaca connection established!")
        
        # Get account info
        account = broker.get_account()
        logger.info(f"Account ID: {account.get('id', 'N/A')}")
        logger.info(f"Buying Power: ${account.get('buying_power', 0):,.2f}")
        logger.info(f"Portfolio Value: ${account.get('portfolio_value', 0):,.2f}")
        logger.info(f"Cash: ${account.get('cash', 0):,.2f}")
        
        # Get clock
        clock = broker.get_clock()
        logger.info(f"Market Open: {clock.get('is_open', False)}")
        
        # Get positions
        positions = broker.get_positions()
        logger.info(f"Current Positions: {len(positions)}")
        
        for pos in positions:
            logger.info(f"  - {pos.symbol}: {pos.qty} shares @ ${pos.current_price:.2f}")
        
        await broker.shutdown()
        
        return True
    else:
        logger.error("FAILED: Could not connect to Alpaca")
        return False


if __name__ == '__main__':
    print("""
============================================================
                                                             
         ALPACA CONNECTION TEST
                                                             
    Testing your API keys and connection
                                                             
============================================================
    """)
    
    success = asyncio.run(test_alpaca_connection())
    
    if success:
        print("\nSUCCESS! Your Alpaca keys are working correctly.")
        print("You can now run the full paper trading system.")
    else:
        print("\nFAILED! Check your API keys in .env.alpaca")
        print("Make sure you're using paper trading keys.")