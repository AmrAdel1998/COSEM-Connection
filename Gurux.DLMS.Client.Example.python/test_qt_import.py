import sys
from pathlib import Path
script_dir = Path(__file__).parent
sys.path.insert(0, str(script_dir))

print("--- Checking dlms_gui_qt.py structure ---")
print("1. Does the file exist? {}".format((script_dir / 'dlms_gui_qt.py').exists()))

print("\n2. Attempting import...")
try:
    from dlms_gui_qt import DLMSGUI
    print("Import succeeded!")
    
    print("\n3. Checking for attributes on class...")
    attrs = dir(DLMSGUI)
    print("DLMSGUI attributes (first 20 non-private): {}".format([a for a in attrs if not a.startswith('__')][:20]))
    print("Has _build_helpers? {}".format('_build_helpers' in attrs))
    print("Has save_assoc_view? {}".format('save_assoc_view' in attrs))
    
    print("\n4. Checking DLMSGUI.__dict__ keys...")
    print("Keys in DLMSGUI.__dict__ (first 20 non-private): {}".format([k for k in DLMSGUI.__dict__.keys() if not k.startswith('__')][:20]))
    
except Exception as e:
    print("Import failed!")
    print("Error type: {}".format(type(e).__name__))
    print("Message: {}".format(e))
    import traceback
    print("\nTraceback:")
    traceback.print_exc()
