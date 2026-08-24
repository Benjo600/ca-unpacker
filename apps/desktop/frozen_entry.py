"""PyInstaller entry script.

Do not freeze apps/desktop/__main__.py. PyInstaller names the entry script
__main__, and analysing the package's own __main__.py drops apps.desktop.app
from the bundle (InvalidSourceModule). That is the boot error
"No module named 'apps.desktop.app'".
"""

from apps.desktop.app import main

if __name__ == "__main__":
    main()
