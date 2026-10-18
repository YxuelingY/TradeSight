import py_compile
import sys

files = [
    "d:/code/TradeSight/ui/main_window.py",
    "d:/code/TradeSight/data/fetcher.py",
    "d:/code/TradeSight/ui/chart_widget.py",
]

for f in files:
    try:
        py_compile.compile(f, doraise=True)
        print(f"OK: {f}")
    except py_compile.PyCompileError as e:
        print(f"ERROR: {f}: {e}")
        sys.exit(1)

print("All syntax OK")