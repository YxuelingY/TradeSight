import sys
import traceback

try:
    from ui.main_window import MainWindow
    print("MainWindow imported OK")
except Exception as e:
    print(f"Import failed: {e}")
    traceback.print_exc()