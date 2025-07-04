# runtime_debug.py
# Check if get_current_price is actually available at runtime

import sys
import importlib

def test_monitor_imports():
    """Test importing monitor module and checking function availability"""
    
    print("🔍 Testing monitor module imports...")
    
    try:
        # Import monitor module
        import monitor
        print("✅ Successfully imported monitor module")
        
        # Check if get_current_price exists
        if hasattr(monitor, 'get_current_price'):
            print("✅ get_current_price function exists in monitor module")
            
            # Check if it's callable
            if callable(monitor.get_current_price):
                print("✅ get_current_price is callable")
                
                # Try to call it with test parameters
                try:
                    result = monitor.get_current_price("BTCUSDT", {})
                    print(f"✅ Function call successful, returned: {result}")
                except Exception as e:
                    print(f"⚠️ Function call failed: {e}")
            else:
                print("❌ get_current_price is not callable")
        else:
            print("❌ get_current_price function NOT found in monitor module")
            print(f"Available functions: {[attr for attr in dir(monitor) if not attr.startswith('_') and callable(getattr(monitor, attr))]}")
        
        # Check get_current_price_enhanced
        if hasattr(monitor, 'get_current_price_enhanced'):
            print("✅ get_current_price_enhanced exists")
            
            # Try to inspect the function to see if it can access get_current_price
            import inspect
            try:
                source = inspect.getsource(monitor.get_current_price_enhanced)
                if 'get_current_price(' in source:
                    print("✅ get_current_price_enhanced contains call to get_current_price")
                else:
                    print("❌ get_current_price_enhanced does not contain call to get_current_price")
            except Exception as e:
                print(f"⚠️ Could not inspect source: {e}")
        else:
            print("❌ get_current_price_enhanced NOT found")
            
    except ImportError as e:
        print(f"❌ Failed to import monitor: {e}")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")

def test_function_in_context():
    """Test calling the function in the same context as the error"""
    
    print("\n🧪 Testing function call in similar context...")
    
    try:
        # Try to replicate the exact call that's failing
        from monitor import get_current_price_enhanced
        
        # Test with empty live_candles (similar to error condition)
        result = get_current_price_enhanced("1000APUUSDT", {})
        print(f"✅ Direct call to get_current_price_enhanced succeeded: {result}")
        
    except NameError as e:
        print(f"❌ NameError caught (this is the issue!): {e}")
        
        # This confirms the exact error we're seeing
        print("🎯 This confirms the runtime issue!")
        
    except Exception as e:
        print(f"⚠️ Other error: {e}")

def check_module_globals():
    """Check what's in the monitor module's global namespace"""
    
    print("\n🔍 Checking monitor module globals...")
    
    try:
        import monitor
        
        # Check globals in monitor module
        monitor_globals = dir(monitor)
        
        if 'get_current_price' in monitor_globals:
            print("✅ get_current_price is in monitor globals")
        else:
            print("❌ get_current_price is NOT in monitor globals")
            
        # Show all functions starting with 'get_current'
        get_current_funcs = [name for name in monitor_globals if name.startswith('get_current')]
        print(f"Functions starting with 'get_current': {get_current_funcs}")
        
    except Exception as e:
        print(f"❌ Error checking globals: {e}")

if __name__ == "__main__":
    test_monitor_imports()
    test_function_in_context()
    check_module_globals()
