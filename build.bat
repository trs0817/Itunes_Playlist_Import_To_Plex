@echo off
python -m PyInstaller ^
    --onedir ^
    --name ItunesToPlex ^
    --distpath dist\ItunesToPlex ^
    --icon=icon.ico ^
    --version-file=version_info.txt ^
    --add-data "icon.ico;." ^
    main.py
echo.
echo Build complete. Run: dist\ItunesToPlex\ItunesToPlex\ItunesToPlex.exe
