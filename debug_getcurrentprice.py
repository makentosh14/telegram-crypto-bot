# debug_getcurrentprice.py
# Run this to find where get_current_price is being called

import os
import re

def find_get_current_price_calls():
    """Find all calls to get_current_price in Python files"""
    
    # Files to check
    files_to_check = [
        'active_trade_scanner.py',
        'monitor.py',
        'universal_trailing_stop_fix.py',
        'main.py',
        'bybit_api.py'
    ]
    
    print("🔍 Searching for get_current_price calls...")
    
    for filename in files_to_check:
        if os.path.exists(filename):
            print(f"\n📁 Checking {filename}:")
            
            try:
                with open(filename, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                
                for line_num, line in enumerate(lines, 1):
                    # Look for get_current_price calls (not imports or definitions)
                    if 'get_current_price(' in line and not line.strip().startswith('#'):
                        # Exclude function definitions and imports
                        if not ('def get_current_price' in line or 'from ' in line or 'import ' in line):
                            print(f"  ⚠️  Line {line_num}: {line.strip()}")
                            
                            # Show context (lines before and after)
                            start = max(0, line_num - 3)
                            end = min(len(lines), line_num + 2)
                            print(f"     Context:")
                            for i in range(start, end):
                                marker = " >>> " if i == line_num - 1 else "     "
                                print(f"     {i+1:3d}{marker}{lines[i].rstrip()}")
                            print()
                        
            except Exception as e:
                print(f"  ❌ Error reading {filename}: {e}")
        else:
            print(f"  📄 {filename} not found")
    
    print("\n" + "="*50)
    print("SEARCH COMPLETE")
    print("="*50)

if __name__ == "__main__":
    find_get_current_price_calls()
