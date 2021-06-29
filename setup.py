# coding:utf-8

import sys
import os
import cx_Freeze
from cx_Freeze import setup, Executable
import PyQt5
from ctrl import MY_VERSION

pyqt5_path = PyQt5.__path__[0]
pyqt5_platform_dll_path = os.path.join(pyqt5_path, "Qt\\plugins\\platforms\\qwindows.dll")

if cx_Freeze.version == '6.2':
    # https://stackoverflow.com/questions/62951554/cx-freeze-gives-typeerror-expected-str-bytes-or-os-pathlike-object-not-nonety
    print("cx_Freeze 6.2 has issue, quit! use cx_Freeze 6.1 instead")
    sys.exit(1)

if sys.version[0] == '2':
    # causes syntax error on py2
    print('python 2 is not supported!')
    sys.exit(1)

# Dependencies are automatically detected, but it might need fine tuning.
# do not include PyQt5 to "avoid ImportError: No module named 'PyQt5.Qt'"
build_exe_options = {
    "build_exe": f"build/Tester V{MY_VERSION}/",
    "optimize": 1,
    "packages": ["os", "sys", "logging", "traceback"],
    "excludes": ["tkinter", "matplotlib", "PyQt4"],
    "include_files": [
        # ('testmodbus_ui.ui', ''),
        ('config.txt', ''),
        (pyqt5_platform_dll_path, "platforms\qwindows.dll"),
        ('Test.ico', ''),
    ],
    "include_msvcr": True,
}

# GUI applications require a different base on Windows (the default is for a
# console application).
base = None
if sys.platform == "win32":
    # base = "Win32GUI"
    base = "Console"

setup(name=f"Tester V{MY_VERSION}",
      version=f"{MY_VERSION}",
      description=f"Tester V{MY_VERSION}",
      options={"build_exe": build_exe_options},
      executables=[Executable("ctrl.py", base=base, targetName="ctrl",
                              icon="Test.ico")])
