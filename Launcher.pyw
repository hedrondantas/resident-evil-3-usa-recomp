"""Double-click to open the Resident Evil 3: Nemesis (USA) Recompiled launcher.

The launcher itself lives in launcher/re3_launcher.py. It needs Python 3.11+
with tkinter, which the python.org and Microsoft Store installers include.
"""

import sys
from pathlib import Path

if sys.version_info < (3, 11):
    import tkinter
    from tkinter import messagebox

    tkinter.Tk().withdraw()
    messagebox.showerror(
        "Launcher",
        "This launcher needs Python 3.11 or newer.\n"
        f"Found Python {sys.version.split()[0]}.",
    )
    sys.exit(1)

sys.path.insert(0, str(Path(__file__).resolve().parent / "launcher"))

import re3_launcher  # noqa: E402

re3_launcher.main()
