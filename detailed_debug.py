# detailed_debug.py
# More detailed analysis of the get_current_price issue

import os
import re

def analyze_monitor_file():
    """Analyze monitor.py file structure"""
    
    filename = 'monitor.py'
    
    if not os.path.exists(filename):
        print(f"❌ {filename} not found")
        return
    
    print(f"🔍 Analyzing {filename}...")
    
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        print(f"📊 Total lines: {len(lines)}")
        
        # Find function definitions
        print("\n📋 Function definitions found:")
        for line_num, line in enumerate(lines, 1):
            if line.strip().startswith('def get_current_price'):
                print(f"  ✅ Line {line_num}: {line.strip()}")
                
                # Show the next few lines to see the function signature
                for i in range(line_num, min(line_num + 5, len(lines))):
                    print(f"     {i:3d}: {lines[i-1].rstrip()}")
                print()
        
        # Find calls to get_current_price
        print("📋 Function calls found:")
        call_count = 0
        for line_num, line in enumerate(lines, 1):
            if 'get_current_price(' in line and not line.strip().startswith('#'):
                if not ('def get_current_price' in line or 'from ' in line or 'import ' in line):
                    call_count += 1
                    print(f"  🔧 Line {line_num}: {line.strip()}")
                    
                    # Show context around the call
                    start = max(0, line_num - 2)
                    end = min(len(lines), line_num + 2)
                    print(f"     Context:")
                    for i in range(start, end):
                        marker = " >>> " if i == line_num - 1 else "     "
                        print(f"     {i+1:3d}{marker}{lines[i].rstrip()}")
                    print()
        
        print(f"📊 Total function calls found: {call_count}")
        
        # Check for indentation issues or scope problems
        print("\n🔍 Checking for scope issues around line 488:")
        
        if len(lines) >= 488:
            start = max(0, 480)
            end = min(len(lines), 495)
            
            print(f"Lines {start+1}-{end}:")
            for i in range(start, end):
                marker = " >>> " if i == 487 else "     "  # Line 488 is index 487
                print(f"{i+1:3d}{marker}{lines[i].rstrip()}")
        
    except Exception as e:
        print(f"❌ Error reading {filename}: {e}")

def check_indentation_and_scope():
    """Check for indentation/scope issues that might cause the error"""
    
    filename = 'monitor.py'
    
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Try to compile the file to check for syntax errors
        try:
            compile(content, filename, 'exec')
            print("✅ monitor.py compiles without syntax errors")
        except SyntaxError as e:
            print(f"❌ Syntax error in monitor.py: {e}")
            print(f"   Line {e.lineno}: {e.text}")
            return
        
        # Check if get_current_price is defined before it's called
        lines = content.split('\n')
        
        get_current_price_defined = False
        definition_line = 0
        
        for line_num, line in enumerate(lines, 1):
            if line.strip().startswith('def get_current_price('):
                get_current_price_defined = True
                definition_line = line_num
                break
        
        if get_current_price_defined:
            print(f"✅ get_current_price defined at line {definition_line}")
            
            # Check if line 488 comes after the definition
            if 488 > definition_line:
                print(f"✅ Call at line 488 comes after definition (line {definition_line})")
            else:
                print(f"❌ Call at line 488 comes BEFORE definition (line {definition_line})")
                
        else:
            print("❌ get_current_price function definition not found")
            
    except Exception as e:
        print(f"❌ Error checking scope: {e}")

if __name__ == "__main__":
    analyze_monitor_file()
    print("\n" + "="*50)
    check_indentation_and_scope()
