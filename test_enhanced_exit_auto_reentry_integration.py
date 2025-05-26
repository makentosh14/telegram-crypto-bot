# test_enhanced_exit_auto_reentry_integration.py

def test_enhanced_exit_reentry_integration():
    print("🔍 Testing enhanced_exit.py integration with auto_reentry...")

    passed = 0
    failed = 0

    try:
        with open("enhanced_exit.py", "r") as f:
            content = f.read()

        checks = {
            "log_exit import": "from auto_reentry import log_exit" in content,
            "update_reentry_performance import": "update_reentry_performance" in content,
            "calls log_exit": "log_exit(" in content,
            "calls update_reentry_performance": "update_reentry_performance(" in content,
            "calculates profit_pct": "profit_pct =" in content or "calculate profit" in content
        }

        for label, result in checks.items():
            if result:
                print(f"✅ {label}")
                passed += 1
            else:
                print(f"❌ {label}")
                failed += 1

        print(f"\nResults: {passed} passed, {failed} failed")

        if failed == 0:
            print("✅ All auto_reentry integration checks passed in enhanced_exit.py!")
        else:
            print("⚠️ Some reentry integrations might be incomplete.")

    except Exception as e:
        print(f"❌ Error while testing: {e}")

if __name__ == "__main__":
    test_enhanced_exit_reentry_integration()
