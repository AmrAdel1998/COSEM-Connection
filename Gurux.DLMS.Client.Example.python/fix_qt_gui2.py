import sys
from pathlib import Path
script_dir = Path(__file__).parent
file_path = script_dir / "dlms_gui_qt.py"
backup_path = script_dir / "dlms_gui_qt.py.backup"

print("--- Fixing dlms_gui_qt.py class structure again ---")
# Read the file again
print("Reading original backup file")
with open(backup_path, "r", encoding="utf-8") as f:
    lines = f.readlines()

# Find correct split points
task_dialog_start_idx = -1
for i, line in enumerate(lines):
    if line.strip() == "class TaskDialog(QDialog):":
        task_dialog_start_idx = i
        print(f"TaskDialog starts at line {i+1}")
        break

# Find def main()
main_start_idx = -1
for i, line in enumerate(lines):
    if line.strip() == "def main():":
        main_start_idx = i
        print(f"main() starts at line {i+1}")
        break

# Now the correct parts are:
# part 1: everything from 0 to task_dialog_start_idx → this is first half of DLMSGUI
# part 2: everything from task_dialog_end_idx (which is main_start_idx) → second half of DLMSGUI
# part 3: TaskDialog itself
# part 4: main() and if __name__...

print("Split points found!")
print(f"Part 1: 0 → {task_dialog_start_idx-1}")
print(f"Part 2: {main_start_idx} → end (but stop before part 4)")
print(f"Part 3: {task_dialog_start_idx} → {main_start_idx-1} (TaskDialog class)")
print(f"Part4: main() and onwards")

# Now let's extract part2: from main_start_idx backwards until we find a blank line + comment that starts with "# ----------------"
# Wait no— let's look for what comes right after part1 (before TaskDialog ends), i.e., from line 1206 (task_dialog_start_idx) until line main_start_idx - 1 is part3 (TaskDialog), and from line 1 to line task_dialog_start_idx-1 is part1 (first DLMSGUI half)
# And the second DLMSGUI half is... wait no! Wait in the original backup file:
# Original backup file line order is:
# 1-1205: part1 (DLMSGUI up to _parse_action_with_list_response etc.)
# 1206-2125: TaskDialog class
# 2126-2362: second DLMSGUI half (_build_helpers(), _type_name(), etc.) + main()

# Wait a minute THAT'S THE PROBLEM! So in the original file, TaskDialog was between two halves of DLMSGUI!
# So the correct order should be:
# Part1 (1-1205) + second DLMSGUI half (2126-2362 but WITHOUT main()) + TaskDialog class (1206-2125) + main() and if __name__!

print("Correcting split logic now...")
# Find where the second DLMSGUI half ends and main() starts!
# So second DLMSGUI half is from line main_start_idx up until...
# Let's read original backup's line main_start_idx and around!
print("Looking at original backup lines 2100-2150")
for i in range(2100, 2150):
    if i < len(lines):
        print(f"{i+1}: {lines[i].strip()}")

# Okay perfect! In original backup line 2126 is the def _build_helpers()! Yes! So second half of DLMSGUI starts at line 2126!
# So let's find out in original backup line numbers:
# part1 = 0 to task_dialog_start_idx-1 (0→1204)
# part_dlms_second = main_start_idx (2125) up until ... let's find where in original backup, after part_dlms_second, comes def main()!
# Wait original backup line numbers: let's find "def main" in original backup
original_main_idx = -1
for i, line in enumerate(lines):
    if line.strip() == "def main():":
        original_main_idx = i
        break

# So part_dlms_second is from original_main_idx's line number in backup (which is where _build_helpers starts, 2125 in 0-index) up until just before def main()!
# Let's find in backup: lines from original_main_idx until we hit "def main()"
dlms_second_end_idx = original_main_idx
for i in range(original_main_idx, len(lines)):
    if lines[i].strip() == "def main():":
        dlms_second_end_idx = i
        print(f"Found end of second DLMSGUI half at line {dlms_second_end_idx+1}")
        break

part1 = lines[:task_dialog_start_idx]
part_dlms_second = lines[original_main_idx:dlms_second_end_idx]
part_taskdialog = lines[task_dialog_start_idx:original_main_idx]
part_main = lines[dlms_second_end_idx:]

fixed_lines = part1 + part_dlms_second + part_taskdialog + part_main

print("Writing fixed file!")
with open(file_path, "w", encoding="utf-8") as f:
    f.writelines(fixed_lines)
print("Successfully fixed dlms_gui_qt.py!")
