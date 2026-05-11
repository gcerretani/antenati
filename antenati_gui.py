#!/usr/bin/env python3
"""PyInstaller entry point for the Tkinter GUI.

This file deliberately stays at the repository root so that the existing
``pyinstaller ... antenati_gui.py`` invocation, the resulting binary name
(``antenati_gui[.exe]``) and the download instructions for end users are
all preserved across the move to a ``src/antenati`` package layout.
"""

from antenati.gui import main

if __name__ == '__main__':
    main()
