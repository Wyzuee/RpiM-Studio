from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "RπM Studio"
APP_DIR_NAME = "RpiM Studio"


def app_data_root() -> Path:
    if sys.platform == 'darwin':
        root = Path.home() / 'Library' / 'Application Support' / APP_DIR_NAME
    elif os.name == 'nt':
        base = os.environ.get('APPDATA') or os.environ.get('LOCALAPPDATA') or str(Path.home())
        root = Path(base) / APP_DIR_NAME
    else:
        base = os.environ.get('XDG_DATA_HOME')
        root = (Path(base) if base else Path.home() / '.local' / 'share') / APP_DIR_NAME
    root.mkdir(parents=True, exist_ok=True)
    return root



def accounts_root() -> Path:
    path = app_data_root() / "accounts"
    path.mkdir(parents=True, exist_ok=True)
    return path


def account_data_root(account_id: int | str) -> Path:
    path = accounts_root() / str(account_id)
    path.mkdir(parents=True, exist_ok=True)
    (path / "avatars").mkdir(parents=True, exist_ok=True)
    (path / "reports").mkdir(parents=True, exist_ok=True)
    (path / "cache").mkdir(parents=True, exist_ok=True)
    return path


def logs_root() -> Path:
    path = app_data_root() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path
