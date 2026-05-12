import sys
from pathlib import Path
script_dir = Path(__file__).parent
file_path = script_dir / "dlms_gui_qt.py"

print("--- Checking class structure ---")

with open(file_path, "r", encoding="utf-8") as f:
    lines = f.readlines()

in_class = False
class_indent = None
class_start_line = None
for i, line in enumerate(lines):
    stripped = line.lstrip()
    if stripped.startswith("class DLMSGUI(QMainWindow)"):
        in_class = True
        class_start_line = i + 1  # 1-based
        class_indent = len(line) - len(stripped)
        print(f"Class DLMSGUI starts at line {class_start_line}, indent={class_indent}")
        continue
    
    if in_class:
        if not stripped:
            continue
        if stripped.startswith("#"):
            continue
        
        current_indent = len(line) - len(stripped)
        # Check if this should be in class
        if stripped[0].isalpha() and current_indent <= class_indent:
            # This is a top-level definition, so class should have ended!
            print(f"WARNING: Possible end of class at line {i+1} (indent={current_indent})")
            print(f"  Line content: {stripped[:80]}")
            in_class = False
            break
        # Also check def to make sure they have correct indentation
        if stripped.startswith("def "):
            if current_indent < class_indent + 4:  # Should be 4 spaces indented inside class
                print(f"WARNING: def at line {i+1} has indent={current_indent}, but class indent is {class_indent}")
                print(f"  Content: {stripped[:80]}")

# Now let's check where _build_helpers is located and its indentation
print("\n--- Checking _build_helpers ---")
for i, line in enumerate(lines):
    stripped = line.lstrip()
    if "_build_helpers" in stripped:
        print(f"_build_helpers found at line {i+1}")
        print(f"  Full line: {repr(line)}")
        print(f"  Indent: {len(line) - len(stripped)}")
        print(f"  Class indent: {class_indent}")
        if class_indent is not None:
            print(f"  Is inside class? {(len(line) - len(stripped)) > class_indent}")
