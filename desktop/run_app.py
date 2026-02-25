#!/usr/bin/env python3
"""Entry point for PyInstaller bundled app."""
import multiprocessing

from undistract_desktop.app import main

if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
