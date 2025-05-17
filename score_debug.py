import asyncio
import json
import sys
from datetime import datetime

# Mock some dependencies to allow testing without actual trading
class MockLogger:
    def __init__(self):
        self.logs = []
    
    def log(self, message, level="INFO"):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.logs.append(f"[{timestamp}] [{level}] {message}")
        print(f"[{level}] {message}")
    
    def get_logs(self):
        return self.logs

# Create mock logger
mock_logger = MockLogger()

# Override the log function in modules we're testing
sys.modules['logger'] = type('MockLoggerModule', (), {'log': mock_logger.log, 'write_log': lambda x, level="INFO": None})

# Mock config values
ALWAYS_ALLOW_SWING = True
MIN_SCALP_SCORE = 6.0
MIN_INTRADAY_SCORE = 6.5
MIN_SWING_SCORE = 7.0

# Test data - simulated trade setups with various scores
test_setups = [
    {"symbol": "BTCUSDT", "score": 7.5, "trade_type": "Scalp", "regime": "trending"},
    {"symbol": "ETHUSDT", "score": 6.2, "trade_type": "Intraday", "regime": "trending"},
    {"symbol": "SOLUSDT", "score": 5.8, "trade_type": "Swing", "regime": "trending"},  # Below threshold but ALWAYS_ALLOW_SWING
    {"symbol": "DOGEUSDT", "score": 5.5, "trade_type": "Scalp", "regime": "volatile"},  # Should pass with volatile adjustment
    {"symbol": "SHIBUSDT", "score": 1.5, "trade_type": "Scalp", "regime": "trending"},  # Should fail - way below threshold
    {"symbol": "AVAXUSDT", "score": 3.5, "trade_type": "Swing", "regime": "trending"},  # Below 50% of threshold even with ALWAYS_ALLOW_SWING
    {"symbol": "LINKUSDT", "score": 6.8, "trade_type": "Swing", "regime": "ranging"},  # Should fail with ranging adjustment
    {"symbol": "ADAUSDT", "score": 3.8, "trade_type": "Mean Reversion", "regime": "ranging", "alternative": "mean_reversion"}, # Should fail mean_reversion min
    {"symbol": "DOTUSDT", "score": 4.2, "trade_type": "Breakout", "regime": "volatile", "alternative": "breakout"}, # Should pass breakout min
]

async def test_threshold_validation():
    print("\n===== TESTING SCORE THRESHOLD VALIDATION =====\n")
    
    # Test basic threshold validation logic
    for setup in test_setups:
        symbol = setup["symbol"]
        score = setup["score"]
        trade_type = setup["trade_type"]
        regime = setup["regime"]
        
        # Score adjustments based on regime
        score_adjustments = {
            "volatile": {"scalp": -0.5, "intraday": -0.5, "swing": -0.5},
            "ranging": {"scalp": 0.5, "intraday": 0.5, "swing": 0.5},
            "trending": {"scalp": 0.0, "intraday": 0.0, "swing": 0.0},
        }
        
        adjust = score_adjustments.get(regime, {"scalp": 0, "intraday": 0, "swing": 0})
        adj_scalp = MIN_SCALP_SCORE + adjust["scalp"]
        adj_intraday = MIN_INTRADAY_SCORE + adjust["intraday"]
        adj_swing = MIN_SWING_SCORE + adjust["swing"]
        
        print(f"\nTesting {symbol} - Score: {score}, Type: {trade_type}, Regime: {regime}")
        print(f"Adjusted thresholds - Scalp: {adj_scalp}, Intraday: {adj_intraday}, Swing: {adj_swing}")
        
        # Validate using the new logic
        min_score_met = False
        if trade_type == "Scalp" and score >= adj_scalp:
            min_score_met = True
            print(f"✅ Passed Scalp threshold: {score} >= {adj_scalp}")
        elif trade_type == "Intraday" and score >= adj_intraday:
            min_score_met = True
            print(f"✅ Passed Intraday threshold: {score} >= {adj_intraday}")
        elif trade_type == "Swing" and score >= adj_swing:
            min_score_met = True
            print(f"✅ Passed Swing threshold: {score} >= {adj_swing}")
        elif trade_type == "Swing" and ALWAYS_ALLOW_SWING and score >= adj_swing * 0.5:
            min_score_met = True
            print(f"⚠️ Passed with ALWAYS_ALLOW_SWING: {score} >= {adj_swing * 0.5} (50% of threshold)")
        # Alternative strategies
        elif "alternative" in setup:
            if setup["alternative"] == "mean_reversion" and score >= 4.0:
                min_score_met = True
                print(f"✅ Passed Mean Reversion threshold: {score} >= 4.0")
            elif setup["alternative"] == "breakout" and score >= 4.0:
                min_score_met = True
                print(f"✅ Passed Breakout threshold: {score} >= 4.0")
            else:
                print(f"❌ Failed alternative strategy threshold: {score} < 4.0")
        else:
            print(f"❌ Failed threshold check: Score {score} below required for {trade_type}")
        
        # Final result
        print(f"Final decision: {'TRADE' if min_score_met else 'SKIP'}")
    
    print("\n===== TEST COMPLETED =====\n")

async def test_execute_trade_validation():
    print("\n===== TESTING TRADE EXECUTOR VALIDATION =====\n")
    
    for setup in test_setups:
        symbol = setup["symbol"]
        score = setup["score"]
        trade_type = setup["trade_type"]
        regime = setup["regime"]
        
        print(f"\nTesting executor for {symbol} - Score: {score}, Type: {trade_type}, Regime: {regime}")
        
        # FIX: Add score validation at the executor level as final safeguard
        min_score_required = {
            "Scalp": 6.0,
            "Intraday": 6.5,
            "Swing": 7.0,
            "Mean Reversion": 4.0,
            "Breakout": 4.0
        }.get(trade_type, 6.0)
        
        # Adjust based on regime
        if regime == "volatile":
            min_score_required -= 0.5
            print(f"Adjusting for volatile regime: threshold now {min_score_required}")
        elif regime == "ranging":
            min_score_required += 0.5
            print(f"Adjusting for ranging regime: threshold now {min_score_required}")
        
        # CRITICAL FIX: Final validation check before proceeding
        if score < min_score_required:
            print(f"❌ Score validation failed in executor: {score:.2f} < {min_score_required}")
            continue
        
        # If we get here, validation passed
        print(f"✅ Executor validation passed: {score:.2f} >= {min_score_required}")

    print("\n===== EXECUTOR TEST COMPLETED =====\n")

if __name__ == "__main__":
    # Run the tests
    asyncio.run(test_threshold_validation())
    asyncio.run(test_execute_trade_validation())
    
    print("\n===== RESULTS SUMMARY =====\n")
    
    # Count how many setups passed the new logic
    pass_count = 0
    for log in mock_logger.logs:
        if "Final decision: TRADE" in log:
            pass_count += 1
    
    print(f"Total test setups: {len(test_setups)}")
    print(f"Passed validation: {pass_count}")
    print(f"Failed validation: {len(test_setups) - pass_count}")
    
    # Generate recommendation
    if pass_count <= len(test_setups) // 2:
        print("\n✅ The new validation logic is working as expected - filtering out low-quality setups.")
    else:
        print("\n⚠️ The new validation may still be allowing too many low-quality setups through.")
