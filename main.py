from __future__ import annotations

from pathlib import Path
import shutil
import sys
import traceback

from app_paths import APP_NAME, account_data_root, app_data_root, logs_root

BASE = Path(__file__).resolve().parent
DATA_ROOT = app_data_root()
LOG_ROOT = logs_root()
CRASH_LOG = LOG_ROOT / "crash.log"


def excepthook(exc_type, exc_value, exc_tb):
    try:
        with CRASH_LOG.open("a", encoding="utf-8") as f:
            f.write("\n=== RπM STUDIO CRASH ===\n")
            traceback.print_exception(exc_type, exc_value, exc_tb, file=f)
    except Exception:
        pass
    traceback.print_exception(exc_type, exc_value, exc_tb)


sys.excepthook = excepthook

try:
    from PySide6.QtCore import QTimer
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication, QMessageBox
    from auth import AccountStore
    from database.database import Database
    from ui.auth_window import AuthDialog
    from ui.main_window import MainWindow
except Exception as exc:
    try:
        with CRASH_LOG.open("a", encoding="utf-8") as f:
            traceback.print_exc(file=f)
    except Exception:
        pass
    print(f"Başlangıç hatası: {type(exc).__name__}: {exc}")
    print(f"Detaylı kayıt: {CRASH_LOG}")
    raise


class AppController:
    def __init__(self, app: QApplication):
        self.app = app
        self.auth = AccountStore(DATA_ROOT)
        self.window = None
        self.current_account = None

    def start(self):
        account = self.auth.try_auto_login()
        if account:
            self.open_studio(account)
        else:
            QTimer.singleShot(0, self.show_auth)

    def show_auth(self):
        dlg = AuthDialog(self.auth)
        if dlg.exec() != AuthDialog.Accepted or not dlg.account:
            self.app.quit()
            return
        self.open_studio(dlg.account)

    def open_studio(self, account: dict):
        self.current_account = dict(account)
        user_root = account_data_root(account["id"])
        # Upgrade path: the first account may inherit the old pre-account local DB.
        legacy_db = BASE / 'data' / 'live_manager.db'
        account_db = user_root / 'live_manager.db'
        if not account_db.exists() and legacy_db.exists():
            try:
                shutil.copy2(legacy_db, account_db)
            except Exception:
                pass
        db = Database(account_db)
        self.window = MainWindow(
            db,
            BASE,
            account=self.current_account,
            auth_store=self.auth,
            data_dir=user_root,
            logout_callback=self.after_logout,
        )
        self.window.show()

    def after_logout(self):
        self.window = None
        self.current_account = None
        QTimer.singleShot(20, self.show_auth)


app = QApplication(sys.argv)
app.setApplicationName(APP_NAME)
app.setApplicationDisplayName(APP_NAME)
app.setOrganizationName("RpiM Studio")
app.setQuitOnLastWindowClosed(False)
icon_path = BASE / 'assets' / ('rpim_studio.ico' if sys.platform.startswith('win') else 'rpim_studio.png')
if icon_path.exists():
    app.setWindowIcon(QIcon(str(icon_path)))

controller = AppController(app)
controller.start()

try:
    code = app.exec()
except Exception as exc:
    excepthook(type(exc), exc, exc.__traceback__)
    try:
        QMessageBox.critical(None, "RπM Studio - Hata", f"Uygulama durdu.\n\n{exc}\n\nHata kaydı: {CRASH_LOG}")
    except Exception:
        pass
    code = 1
finally:
    try:
        controller.auth.close()
    except Exception:
        pass

sys.exit(code)
