import sys
from pathlib import Path
script_dir = Path(__file__).parent
backup_file = script_dir / "dlms_gui_qt.py.backup"
target_file = script_dir / "dlms_gui_qt.py"

print("ULTRA FINAL FINAL FIX: Correct task_dialog_end!")

with open(backup_file, "r", encoding="utf-8") as f:
    all_lines = f.readlines()

# Correct split points!
task_dialog_start = -1
save_assoc_view_start = -1
build_helpers_start = -1

for i, line in enumerate(all_lines):
    stripped = line.strip()
    if stripped == "class TaskDialog(QDialog):":
        task_dialog_start = i
        print("TaskDialog start at", i+1)
    if stripped == "def save_assoc_view(self):":
        save_assoc_view_start = i
        print("save_assoc_view start at", i+1)
    if stripped == "def _build_helpers(self):":
        build_helpers_start = i
        print("_build_helpers start at", i+1)

# Now correct split points!
dlms_gui_part1 = all_lines[:task_dialog_start]
task_dialog_part = all_lines[task_dialog_start:save_assoc_view_start]
dlms_gui_middle = all_lines[save_assoc_view_start:build_helpers_start]
dlms_gui_part2 = all_lines[build_helpers_start:]

# Now find main_start inside dlms_gui_part2
main_start = -1
for i in range(len(dlms_gui_part2)):
    stripped = dlms_gui_part2[i].strip()
    if stripped.startswith("def main("):
        main_start = i
        break

dlms_gui_final = dlms_gui_part1 + dlms_gui_middle + dlms_gui_part2[:main_start]
main_part = dlms_gui_part2[main_start:]

# Final combined lines!
final_lines = dlms_gui_final + main_part + task_dialog_part

with open(target_file, "w", encoding="utf-8") as f:
    f.writelines(final_lines)

print("SUCCESS: FINAL FIX COMPLETED!")
