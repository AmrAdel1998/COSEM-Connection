import sys
from pathlib import Path
script_dir = Path(__file__).parent
backup_file = script_dir / "dlms_gui_qt.py.backup"
target_file = script_dir / "dlms_gui_qt.py"

print("Fixing dlms_gui_qt.py from backup - moving TaskDialog to end!")

# Read all lines from backup
with open(backup_file, "r", encoding="utf-8") as f:
    all_lines = f.readlines()

# Find TaskDialog start and end
task_dialog_start_line = -1
task_dialog_end_line = -1
in_task_dialog = False

for i, line in enumerate(all_lines):
    stripped = line.strip()
    if stripped == "class TaskDialog(QDialog):":
        task_dialog_start_line = i
        in_task_dialog = True
        print(f"Found TaskDialog start at line {i+1}")
    elif in_task_dialog and (stripped.startswith("def main(") or stripped.startswith("class ")):
        task_dialog_end_line = i
        print(f"Found TaskDialog end at line {i}")
        in_task_dialog = False
        break

if task_dialog_start_line == -1:
    print("ERROR: Could not find TaskDialog!")
    sys.exit(1)

if task_dialog_end_line == -1:
    task_dialog_end_line = len(all_lines)

# Split into parts
part1 = all_lines[:task_dialog_start_line]
task_dialog_part = all_lines[task_dialog_start_line:task_dialog_end_line]
part2 = all_lines[task_dialog_end_line:]

# Now re-order: part1 + part2 + task_dialog_part!
fixed_lines = part1 + part2 + task_dialog_part

# Write to target file!
with open(target_file, "w", encoding="utf-8") as f:
    f.writelines(fixed_lines)

print("Successfully fixed dlms_gui_qt.py! TaskDialog moved to end of file!")
