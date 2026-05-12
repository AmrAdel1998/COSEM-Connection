import sys
from pathlib import Path
script_dir = Path(__file__).parent
backup_file = script_dir / "dlms_gui_qt.py.backup"
target_file = script_dir / "dlms_gui_qt.py"

print("Final fix: Correctly split DLMSGUI and TaskDialog")

# Read all lines from backup
with open(backup_file, "r", encoding="utf-8") as f:
    all_lines = f.readlines()

# Find key points:
# 1. TaskDialog start line
task_dialog_start = -1
# 2. _build_helpers start line (this is where DLMSGUI continues after TaskDialog!)
build_helpers_start = -1

for i, line in enumerate(all_lines):
    stripped = line.strip()
    if stripped == "class TaskDialog(QDialog):":
        task_dialog_start = i
        print(f"TaskDialog starts at: {i+1}")
    if stripped == "def _build_helpers(self):":
        build_helpers_start = i
        print(f"_build_helpers starts at: {i+1}")

if task_dialog_start == -1 or build_helpers_start == -1:
    print("ERROR: Could not find split points!")
    sys.exit(1)

# Now split properly!
# Part1: Lines from 0 → task_dialog_start
dlms_gui_part1 = all_lines[:task_dialog_start]
# Part2: Lines from build_helpers_start → end of DLMSGUI (up to before def main())
# Find where def main starts!
main_start = -1
for i in range(build_helpers_start, len(all_lines)):
    stripped = all_lines[i].strip()
    if stripped.startswith("def main("):
        main_start = i
        break
dlms_gui_part2 = all_lines[build_helpers_start:main_start]
# Part3: TaskDialog: task_dialog_start → build_helpers_start
task_dialog_part = all_lines[task_dialog_start:build_helpers_start]
# Part4: The main() and if __name__ block
main_part = all_lines[main_start:]

# Now combine all in correct order: dlms_gui_part1 + dlms_gui_part2 + main_part + task_dialog_part
final_lines = dlms_gui_part1 + dlms_gui_part2 + main_part + task_dialog_part

# Write to target file
with open(target_file, "w", encoding="utf-8") as f:
    f.writelines(final_lines)

print("SUCCESS: dlms_gui_qt.py fixed completely!")
