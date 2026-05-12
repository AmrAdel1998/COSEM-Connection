import sys
from pathlib import Path
script_dir = Path(__file__).parent
file_path = script_dir / "dlms_gui_qt.py"
backup_path = script_dir / "dlms_gui_qt.py.backup"

print("--- Fixing dlms_gui_qt.py class structure ---")
print(f"Reading {file_path}")
with open(file_path, "r", encoding="utf-8") as f:
    lines = f.readlines()

# Save backup
print(f"Writing backup to {backup_path}")
with open(backup_path, "w", encoding="utf-8") as f:
    f.writelines(lines)

# Now find parts
# Part 1: Start up to just before class TaskDialog(QDialog): at line 1206 (0-index 1205)
# Find the line index where "class TaskDialog(QDialog):" occurs
task_dialog_start_idx = -1
for i, line in enumerate(lines):
    if line.strip() == "class TaskDialog(QDialog):":
        task_dialog_start_idx = i
        print(f"Found TaskDialog class start at line {i+1}")
        break

if task_dialog_start_idx == -1:
    print("ERROR: Could not find TaskDialog class")
    sys.exit(1)

# Now find where TaskDialog class ends
# We'll look for the next class definition or def main()
task_dialog_end_idx = len(lines)
for i in range(task_dialog_start_idx + 1, len(lines)):
    stripped = lines[i].strip()
    if stripped.startswith("def main(") or stripped.startswith("class "):
        task_dialog_end_idx = i
        print(f"Found TaskDialog class end at line {i} (next definition)")
        break

# Now split into three parts
part1 = lines[:task_dialog_start_idx]  # Everything before TaskDialog
part2 = lines[task_dialog_start_idx:task_dialog_end_idx]  # TaskDialog class
part3 = lines[task_dialog_end_idx:]  # Everything after TaskDialog (remaining DLMSGUI methods + main etc)

# Now combine in correct order: part1 (start of DLMSGUI) + part3 (end of DLMSGUI) + part2 (TaskDialog)
fixed_lines = part1 + part3 + part2

print("Writing fixed file...")
with open(file_path, "w", encoding="utf-8") as f:
    f.writelines(fixed_lines)

print("✅ Success! dlms_gui_qt.py fixed!")
print(f"TaskDialog moved to end of file, after DLMSGUI is complete.")
