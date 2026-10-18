import sys

print("Step 1: Importing PyQt6...", flush=True)
from PyQt6.QtWidgets import QApplication
print("Step 1 OK", flush=True)

print("Step 2: Creating QApplication...", flush=True)
app = QApplication(sys.argv)
print("Step 2 OK", flush=True)

print("Step 3: Importing MainWindow...", flush=True)
from ui.main_window import MainWindow
print("Step 3 OK", flush=True)

print("Step 4: Creating window...", flush=True)
w = MainWindow()
print("Step 4 OK", flush=True)

print("Step 5: Showing window...", flush=True)
w.show()
print("Step 5 OK - Window should be visible now", flush=True)

# 不进入事件循环，3秒后自动退出（验证窗口能创建显示）
from PyQt6.QtCore import QTimer
QTimer.singleShot(3000, app.quit)
print("Step 6: Starting event loop (3 seconds)...", flush=True)
app.exec()
print("Step 6 OK - Event loop ended", flush=True)
print("Test completed successfully - Window opened and closed normally", flush=True)