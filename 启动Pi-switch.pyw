# -*- coding: utf-8 -*-
"""Pi-switch 的无窗口启动器。

双击本文件（.pyw）即可直接启动 Pi-switch：
  - Windows 会自动用 pythonw（无窗口版 Python）运行，因此不会弹出黑色命令行窗口。
  - 与运行 pi_switch.py 完全等价；若出错，错误日志仍会写到同目录 error.log。
"""
import os
import runpy

_here = os.path.dirname(os.path.abspath(__file__))
os.chdir(_here)
runpy.run_path(os.path.join(_here, "pi_switch.py"), run_name="__main__")
