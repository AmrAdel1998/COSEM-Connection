import sys
from pathlib import Path
script_dir = Path(__file__).parent
backup_file = script_dir / "dlms_gui_qt.py.backup"
target_file = script_dir / "dlms_gui_qt.py"

print("ULTRA FINAL FIX: Properly split all parts!")

# Read all lines from backup
with open(backup_file, "r", encoding="utf-8") as f:
    all_lines = f.readlines()

# Key indices
task_dialog_start = -1  # class TaskDialog starts
task_dialog_end = -1    # TaskDialog ends
build_helpers_start = -1 # def _build_helpers starts
save_assoc_view_start = -1 # just to confirm

for i, line in enumerate(all_lines):
    stripped = line.strip()
    if stripped == "class TaskDialog(QDialog):":
        task_dialog_start = i
        print(f"TaskDialog starts: {i+1}")
    if task_dialog_start != -1 and task_dialog_end == -1:
        # Look for end of TaskDialog: next def that's not indented at TaskDialog level!
        if stripped.startswith("def ") and not line.startswith("    def "):
            # if it's a def that's not indented 4 spaces!
            # Wait, TaskDialog methods are indented 8 spaces!
            if not line.startswith("        def "): # TaskDialog methods are indented 8 spaces!
                task_dialog_end = i
                print(f"TaskDialog ends: {i}")
    if stripped == "def _build_helpers(self):":
        build_helpers_start = i
        print(f"_build_helpers starts: {i+1}")
    if stripped == "def save_assoc_view(self):":
        save_assoc_view_start = i
        print(f"save_assoc_view starts: {i+1}")

# Now confirm:
print("\nCONFIRMING:")
print(f"save_assoc_view ({save_assoc_view_start}) is between task_dialog_start ({task_dialog_start}) and build_helpers_start ({build_helpers_start})?")
print(f"Answer: {task_dialog_start < save_assoc_view_start < build_helpers_start}")

# Now split properly into:
# part1: from 0 to task_dialog_start → dlms_gui_part1
# part2: from task_dialog_start to task_dialog_end → dlms_gui_middle (other methods like save_assoc_view!)
# part3: from task_dialog_end to build_helpers_start → task_dialog_part (the actual TaskDialog class!)
# part4: from build_helpers_start to end of dlms_gui (before def main()) → dlms_gui_part2
# part5: def main() and __name__ etc → main_part
dlms_gui_part1 = all_lines[:task_dialog_start]
dlms_gui_middle = all_lines[task_dialog_start:task_dialog_end]
task_dialog_part = all_lines[task_dialog_end:build_helpers_start]

# Now find main_part start
main_start = -1
for i in range(build_helpers_start, len(all_lines)):
    stripped = all_lines[i].strip()
    if stripped.startswith("def main("):
        main_start = i
        break

dlms_gui_part2 = all_lines[build_helpers_start:main_start]
main_part = all_lines[main_start:]

# Now combine: dlms_gui_part1 + dlms_gui_middle + dlms_gui_part2 + main_part + task_dialog_part
final_lines = dlms_gui_part1 + dlms_gui_middle + dlms_gui_part2 + main_part + task_dialog_part

# Write final!
with open(target_file, "w", encoding="utf-8") as f:
    f.writelines(final_lines)

print("SUCCESS ULTRA FINAL FIX COMPLETED!")
