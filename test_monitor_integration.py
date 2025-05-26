Test if monitor.py integration is correct
"""

import ast

def test_monitor_integration():
    """Check if monitor.py has reentry integration"""
    
    print("🔍 Testing monitor.py integration...")
    
    try:
        with open('monitor.py', 'r') as f:
            content = f.read()
        
        # Check for imports
        checks = {
            'ENABLE_AUTO_REENTRY import': 'from config import ENABLE_AUTO_REENTRY' in content,
            'auto_reentry imports': 'from auto_reentry import' in content,
            'log_exit_for_reentry function': 'async def log_exit_for_reentry' in content,
            'update_exit_cooldowns call': 'update_exit_cooldowns()' in content,
            'SL reentry logging': 'log_exit_for_reentry(symbol, trade, current_price, "SL_Hit")' in content,
            'Trailing SL logging': 'log_exit_for_reentry(symbol, trade, current_price, "Trailing_SL")' in content,
            'Time exit logging': 'log_exit_for_reentry(symbol, trade, current_price, "Time_Exit")' in content,
        }
        
        passed = 0
        failed = 0
        
        for check, result in checks.items():
            if result:
                print(f"✅ {check}")
                passed += 1
            else:
                print(f"❌ {check}")
                failed += 1
        
        print(f"\nResults: {passed} passed, {failed} failed")
        
        if failed == 0:
            print("\n✅ All integration checks passed!")
        else:
            print("\n⚠️  Some integrations are missing. Please add them.")
            
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    test_monitor_integration()
