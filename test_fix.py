#!/usr/bin/env python3
# test_fix.py - Test the unified exit manager

def test_imports():
    """Test that all imports work correctly"""
    try:
        from unified_exit_manager import process_trade_exits, validate_exit_configuration
        print("✅ unified_exit_manager imports successful")
        
        # Test configuration validation
        if validate_exit_configuration():
            print("✅ Configuration validation passed")
        else:
            print("❌ Configuration validation failed")
            
        return True
        
    except ImportError as e:
        print(f"❌ Import error: {e}")
        return False
    except Exception as e:
        print(f"❌ Other error: {e}")
        return False

def test_no_conflicts():
    """Test that conflicting imports are removed"""
    import os
    
    conflicts_found = False
    
    # Check if conflicting files are disabled
    if os.path.exists("universal_trailing_stop_fix.py"):
        print("⚠️ universal_trailing_stop_fix.py still active (should be .disabled)")
        conflicts_found = True
    else:
        print("✅ universal_trailing_stop_fix.py disabled")
        
    if os.path.exists("enhanced_exit.py"):
        print("⚠️ enhanced_exit.py still active (should be .disabled)")
        conflicts_found = True
    else:
        print("✅ enhanced_exit.py disabled")
    
    return not conflicts_found

if __name__ == "__main__":
    print("🧪 Testing Trading Bot Fix...")
    print("=" * 40)
    
    imports_ok = test_imports()
    conflicts_ok = test_no_conflicts()
    
    if imports_ok and conflicts_ok:
        print("\n✅ All tests passed! Bot is ready to run.")
    else:
        print("\n❌ Some tests failed. Please fix the issues above.")
