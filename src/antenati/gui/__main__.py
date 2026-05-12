"""Module entry point for the Tkinter GUI.

Enables ``python -m antenati.gui`` and serves as the PyInstaller target,
replacing the old ``antenati_gui.py`` shim at the repository root.
"""

from antenati.gui import main

if __name__ == '__main__':
    main()
