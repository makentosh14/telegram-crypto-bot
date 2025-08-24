# pattern_matcher_debug.py
# Comprehensive diagnostic tool for pattern matching issues

import json
import os
from datetime import datetime, timedelta
from logger import log

def diagnose_pattern_matcher():
    """
    Comprehensive diagnosis of why pattern matcher isn't finding patterns
    """
    print("🔍 PATTERN MATCHER DIAGNOSTIC")
    print("=" * 50)
    
    # Issue 1: Check if pattern database exists and has data
    check_pattern_database()
    
    # Issue 2: Check pattern discovery vs pattern matching
    check_pattern_flow()
    
    # Issue 3: Check cooldown issues
    check_cooldown_issues()
    
    # Issue 4: Check pattern detection functionality
    check_pattern_detection()
    
    # Issue 5: Check similarity thresholds
    check_similarity_thresholds()
    
    print("\n💡 RECOMMENDATIONS:")
    provide_recommendations()

def check_pattern_database():
    """Check if pattern database exists and has content"""
    print("\n1. 📁 PATTERN DATABASE CHECK")
    
    # Check pattern_match_memory.json (used by pattern_matcher.py)
    match_db_path = "pattern_match_memory.json"
    if os.path.exists(match_db_path):
        try:
            with open(match_db_path, 'r') as f:
                match_data = json.load(f)
            print(f"✅ Pattern match database exists: {len(match_data)} entries")
            
            if len(match_data) == 0:
                print("❌ ISSUE: Pattern match database is EMPTY!")
                print("   This is why no matches are found - there's nothing to match against!")
            else:
                print(f"📊 Sample patterns in database: {list(match_data.keys())[:5]}")
                
        except Exception as e:
            print(f"❌ Error reading pattern match database: {e}")
    else:
        print("❌ ISSUE: pattern_match_memory.json does NOT exist!")
        print("   This is a MAJOR issue - no database to match against!")
    
    # Check pattern_memory.json (used by pattern_discovery.py)  
    discovery_db_path = "pattern_memory.json"
    if os.path.exists(discovery_db_path):
        try:
            with open(discovery_db_path, 'r') as f:
                discovery_data = json.load(f)
            print(f"✅ Pattern discovery database exists: {len(discovery_data)} patterns")
            
            if len(discovery_data) > 0:
                recent_patterns = [p for p in discovery_data if 
                                 datetime.fromisoformat(p['timestamp'].replace('Z', '+00:00')) > 
                                 datetime.now() - timedelta(days=7)]
                print(f"📅 Recent patterns (last 7 days): {len(recent_patterns)}")
            
        except Exception as e:
            print(f"❌ Error reading pattern discovery database: {e}")
    else:
        print("❌ Pattern discovery database (pattern_memory.json) does NOT exist!")

def check_pattern_flow():
    """Check the flow from pattern discovery to pattern matching"""
    print("\n2. 🔄 PATTERN FLOW CHECK")
    
    print("   Pattern Discovery (pattern_discovery.py)")
    print("   ↓ saves patterns to → pattern_memory.json")
    print("   ↓")
    print("   Pattern Matcher (pattern_matcher.py)") 
    print("   ↓ loads patterns from → pattern_match_memory.json")
    print("   ↓ finds matches")
    
    print("\n❌ MAJOR ISSUE IDENTIFIED:")
    print("   Pattern Discovery saves to: pattern_memory.json")
    print("   Pattern Matcher loads from:  pattern_match_memory.json")
    print("   These are DIFFERENT FILES! The pattern matcher can't see discovered patterns!")

def check_cooldown_issues():
    """Check if cooldown is preventing matches"""
    print("\n3. ⏰ COOLDOWN CHECK")
    
    match_db_path = "pattern_match_memory.json"
    if os.path.exists(match_db_path):
        try:
            with open(match_db_path, 'r') as f:
                match_data = json.load(f)
            
            if match_data:
                now = datetime.now()
                active_cooldowns = 0
                
                for symbol, patterns in match_data.items():
                    for pattern, timestamp_str in patterns.items():
                        try:
                            match_time = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
                            hours_since = (now - match_time).total_seconds() / 3600
                            
                            if hours_since < 6:  # MATCH_COOLDOWN = 6 hours
                                active_cooldowns += 1
                        except:
                            continue
                
                print(f"⏰ Active cooldowns preventing matches: {active_cooldowns}")
                if active_cooldowns > 20:
                    print("❌ ISSUE: Too many active cooldowns may be blocking matches!")
            else:
                print("✅ No cooldown data (database empty)")
                
        except Exception as e:
            print(f"❌ Error checking cooldowns: {e}")
    else:
        print("✅ No cooldown file exists")

def check_pattern_detection():
    """Check if pattern detection is working"""
    print("\n4. 🔍 PATTERN DETECTION CHECK")
    
    print("   Pattern detector should be finding patterns like:")
    print("   - hammer, doji, engulfing, morning_star, etc.")
    print("   - If detect_pattern() returns None consistently, that's an issue")
    print("   - Check your pattern_detector.py logs for pattern detection activity")

def check_similarity_thresholds():
    """Check if similarity thresholds are too strict"""
    print("\n5. 📊 SIMILARITY THRESHOLD CHECK")
    
    print("   Current thresholds in pattern_matcher.py:")
    print("   - Alert threshold: 70% similarity (match_score > 0.7)")
    print("   - Trade threshold: 85% similarity (match_score > 0.85)")
    print("   - These might be TOO STRICT for crypto markets")
    print("   - Consider lowering to 50% and 70% respectively")

def provide_recommendations():
    """Provide specific recommendations to fix the issues"""
    
    print("1. 🔧 FIX DATABASE MISMATCH:")
    print("   Update pattern_matcher.py to load from 'pattern_memory.json' instead of 'pattern_match_memory.json'")
    print("   OR modify pattern_discovery.py to save to 'pattern_match_memory.json'")
    
    print("\n2. 📊 LOWER SIMILARITY THRESHOLDS:")
    print("   In pattern_matcher.py, change:")
    print("   - if match_score > 0.7: → if match_score > 0.5:")
    print("   - if match_score > 0.85: → if match_score > 0.7:")
    
    print("\n3. 🕒 REDUCE COOLDOWN:")
    print("   MATCH_COOLDOWN = 6 hours might be too long")
    print("   Consider reducing to 2-3 hours for more frequent matches")
    
    print("\n4. 🔍 ADD DEBUG LOGGING:")
    print("   Add more logging to see what's happening in pattern_match_scan()")
    
    print("\n5. 📈 CHECK PATTERN DISCOVERY:")
    print("   Verify that pattern_discovery_scan() is actually finding and saving patterns")

# Quick fix functions
def fix_database_path():
    """Generate code to fix the database path mismatch"""
    print("\n🔧 QUICK FIX - Update pattern_matcher.py:")
    print("Change line:")
    print("   PATTERN_DB_PATH = \"pattern_match_memory.json\"")
    print("To:")
    print("   PATTERN_DB_PATH = \"pattern_memory.json\"")

def add_debug_logging():
    """Generate enhanced logging for pattern_matcher.py"""
    
    debug_code = '''
# Add this enhanced debug version to pattern_matcher.py:

async def pattern_match_scan_debug(symbols):
    """Enhanced debug version with detailed logging"""
    pattern_stats["scans"] += 1
    
    log(f"🔍 PATTERN MATCHER: Starting scan of {len(symbols)} symbols")
    
    # Load pattern database and recent matches
    patterns_db = load_pattern_memory()
    
    log(f"📊 Pattern database loaded: {len(patterns_db)} patterns")
    if patterns_db:
        pattern_types = list(patterns_db.keys())
        log(f"   Available patterns: {pattern_types[:10]}...")  # Show first 10
    else:
        log("❌ CRITICAL: Pattern database is EMPTY! No patterns to match against!")
        return
    
    matches_found = 0
    patterns_detected = 0
    symbols_with_candles = 0
    
    for symbol in symbols:
        try:
            # Get candles and detect pattern
            from websocket_candles import live_candles
            
            if symbol not in live_candles or not live_candles[symbol].get("5"):
                continue
                
            symbols_with_candles += 1
            candles = list(live_candles[symbol]["5"])
            if len(candles) < 30:
                continue
                
            # Detect current pattern
            current_pattern = detect_pattern(candles)
            if current_pattern:
                patterns_detected += 1
                log(f"🎯 Pattern detected on {symbol}: {current_pattern}")
                
                # Check if this pattern exists in database
                if current_pattern in patterns_db:
                    log(f"✅ {symbol}: Pattern {current_pattern} exists in database")
                    
                    # Check cooldown
                    cooldown_check = check_cooldown_status(symbol, current_pattern)
                    if not cooldown_check['blocked']:
                        # Analyze context and similarity
                        match_score = analyze_pattern_match(symbol, current_pattern, candles, patterns_db)
                        if match_score > 0.5:  # Lowered threshold for debugging
                            matches_found += 1
                            log(f"🎊 MATCH FOUND: {symbol} - {current_pattern} (score: {match_score:.2f})")
                    else:
                        log(f"⏰ {symbol}: Pattern {current_pattern} in cooldown ({cooldown_check['hours_left']:.1f}h left)")
                else:
                    log(f"❌ {symbol}: Pattern {current_pattern} NOT in database")
            
        except Exception as e:
            log(f"❌ Pattern match error for {symbol}: {e}", level="ERROR")
            continue
    
    log(f"📈 SCAN SUMMARY:")
    log(f"   Symbols with candles: {symbols_with_candles}/{len(symbols)}")
    log(f"   Patterns detected: {patterns_detected}")
    log(f"   Matches found: {matches_found}")
    
    if patterns_detected == 0:
        log("❌ No patterns detected - check pattern_detector.py")
    elif matches_found == 0 and patterns_detected > 0:
        log("❌ Patterns detected but no matches - check database or thresholds")
'''
    
    return debug_code

if __name__ == "__main__":
    diagnose_pattern_matcher()
    print("\n" + "="*50)
    fix_database_path()
    print("\n" + "="*50)
    print("Enhanced debug code generated above ☝️")
