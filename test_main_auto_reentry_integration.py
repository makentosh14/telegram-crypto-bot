# test_main_auto_reentry_integration.py

def test_main_reentry_integration():
    print("🔍 Testing main.py integration with auto_reentry...")

    passed = 0
    failed = 0

    try:
        with open("main.py", "r") as f:
            content = f.read()

        checks = {
            "should_reenter import": "should_reenter" in content,
            "handle_reentry import": "handle_reentry" in content,
            "update_reentry_performance import": "update_reentry_performance" in content,
            "calls should_reenter": "await should_reenter" in content,
            "calls handle_reentry": "await handle_reentry" in content,
            "uses is_reentry flag": '"is_reentry": True' in content
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
            print("✅ All auto_reentry integration checks passed in main.py!")
        else:
            print("⚠️  Some reentry integration elements are missing or incomplete.")

    except Exception as e:
        print(f"❌ Error while testing: {e}")

if __name__ == "__main__":
    test_main_reentry_integration()
