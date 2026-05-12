import sys
from pathlib import Path
script_dir = Path(__file__).parent
file_path = script_dir / "dlms_gui_qt.py"
backup_path = script_dir / "dlms_gui_qt.py.backup"

print("Fixing dlms_gui_qt.py class structure again...")
# Read the file again
print("Reading original backup file")
with open(backup_path, "r", encoding="utf-8") as f:
    lines = f.readlines()

# Find correct split points
task_dialog_start_idx = -1
for i, line in enumerate(lines):
    if line.strip() == "class TaskDialog(QDialog):":
        task_dialog_start_idx = i
        print("TaskDialog starts at line", i+1)
        break

# Find def main()
main_start_idx = -1
for i, line in enumerate(lines):
    if line.strip() == "def main():":
        main_start_idx = i
        print("main() starts at line", i+1)
        break

print("Split points found!")

# Okay, now let's find where _build_helpers starts in original backup!
original_build_helpers_idx = -1
for i, line in enumerate(lines):
    if "def _build_helpers" in line:
        original_build_helpers_idx = i
        print("_build_helpers starts at line", i+1)
        break

# So correct split is:
# part 1: 0 to task_dialog_start_idx-1 (first half of DLMSGUI)
# part 2: original_build_helpers_idx to main_start_idx -1 (second half of DLMSGUI)
# part3: task_dialog_start_idx to original_build_helpers_idx -1 (TaskDialog)
# part4: main_start_idx onwards (main() and if __name__)

part1 = lines[:task_dialog_start_idx]
part2 = lines[original_build_helpers_idx:main_start_idx]
part3 = lines[task_dialog_start_idx:original_build_helpers_idx]
part4 = lines[main_start_idx:]

fixed_lines = part1 + part2 + part3 + part4

print("Writing fixed file...")
with open(file_path, "w", encoding="utf-8") as f:
    f.writelines(fixed_lines)
print("Successfully fixed dlms_gui_qt.py!")
