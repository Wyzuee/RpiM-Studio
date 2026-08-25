from __future__ import annotations

import threading

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QInputDialog,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from auth import AccountStore, AuthError


AUTH_QSS = r"""
QDialog#authWindow {
    background: #07101b;
    color: #eef5ff;
    font-family: "Segoe UI";
}
QFrame#brandPanel {
    border: 1px solid rgba(120, 179, 255, 0.16);
    border-radius: 28px;
    background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
        stop:0 #0c1b2f, stop:.48 #101c35, stop:1 #26143c);
}
QFrame#authCard {
    background: rgba(12, 20, 32, 245);
    border: 1px solid rgba(133, 174, 230, 0.18);
    border-radius: 24px;
}
QLabel#brandMark {
    color: #ffffff;
    font-size: 44px;
    font-weight: 900;
}
QLabel#brandTitle {
    color: #ffffff;
    font-size: 32px;
    font-weight: 800;
}
QLabel#brandSub {
    color: #a9bbd3;
    font-size: 14px;
}
QLabel#formTitle {
    color: #ffffff;
    font-size: 28px;
    font-weight: 800;
}
QLabel#formSub, QLabel#hint {
    color: #91a3bb;
    font-size: 13px;
}
QLineEdit {
    min-height: 28px;
    background: #101a28;
    color: #f7fbff;
    border: 1px solid rgba(145, 174, 218, 0.24);
    border-radius: 12px;
    padding: 11px 13px;
    selection-background-color: #6c5ce7;
}
QLineEdit:focus {
    border: 1px solid #63b3ff;
    background: #122034;
}
QPushButton#primary {
    min-height: 30px;
    color: #ffffff;
    font-weight: 800;
    border: 0;
    border-radius: 12px;
    padding: 11px 15px;
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #4f8cff, stop:1 #8a5cff);
}
QPushButton#primary:hover { background: #6b82ff; }
QPushButton#secondary {
    min-height: 28px;
    color: #c9d8eb;
    font-weight: 700;
    border: 1px solid rgba(145,174,218,.18);
    border-radius: 11px;
    padding: 9px 13px;
    background: #121c2a;
}
QPushButton#secondary:hover { background: #18263a; }
QPushButton#segment {
    min-height: 28px;
    color: #c9d8eb;
    font-weight: 800;
    border: 1px solid rgba(145,174,218,.18);
    border-radius: 11px;
    padding: 9px 13px;
    background: #121c2a;
}
QPushButton#segment:hover { background: #18263a; }
QPushButton#segment:checked {
    color:#ffffff;
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #4f8cff, stop:1 #8a5cff);
    border-color: rgba(130,170,255,.34);
}
QPushButton#google {
    min-height: 30px;
    color:#182235;
    font-weight:800;
    border:1px solid #d8e0eb;
    border-radius:12px;
    padding:10px 14px;
    background:#ffffff;
}
QPushButton#google:hover { background:#eef4ff; }
QCheckBox { color: #c5d2e2; spacing: 8px; }
QCheckBox::indicator { width: 18px; height: 18px; }
QCheckBox::indicator:unchecked { border:1px solid #50627b; border-radius:5px; background:#0d1622; }
QCheckBox::indicator:checked { border:1px solid #75a9ff; border-radius:5px; background:#4f8cff; }
"""


class AuthDialog(QDialog):
    authenticated = Signal(dict)
    socialSuccess = Signal(dict)
    socialError = Signal(str)
    passwordResetSent = Signal(str)
    passwordResetReady = Signal(dict)
    passwordResetError = Signal(str)

    def __init__(self, store: AccountStore, parent=None):
        super().__init__(parent)
        self.store = store
        self.account = None
        self._pending_social_publisher = ""
        self.setObjectName("authWindow")
        self.setWindowTitle("RπM Studio • Giriş")
        self.setMinimumSize(900, 580)
        self.resize(980, 640)
        self.setStyleSheet(AUTH_QSS)
        self._build()
        self.socialSuccess.connect(self._social_success)
        self.socialError.connect(self._social_error)
        self.passwordResetSent.connect(self._password_reset_sent)
        self.passwordResetReady.connect(self._password_reset_ready)
        self.passwordResetError.connect(self._password_reset_error)
        self.show_register(False)

    def _build(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(22, 22, 22, 22)
        root.setSpacing(20)

        brand = QFrame()
        brand.setObjectName("brandPanel")
        brand.setMinimumWidth(365)
        brand_layout = QVBoxLayout(brand)
        brand_layout.setContentsMargins(36, 38, 36, 38)
        brand_layout.setSpacing(14)

        mark = QLabel("RπM")
        mark.setObjectName("brandMark")
        title = QLabel("RπM Studio")
        title.setObjectName("brandTitle")
        subtitle = QLabel("TikTok LIVE kontrol merkezi")
        subtitle.setObjectName("brandSub")
        subtitle.setWordWrap(True)
        brand_layout.addWidget(mark)
        brand_layout.addWidget(title)
        brand_layout.addWidget(subtitle)
        brand_layout.addSpacing(22)

        for icon, text in [
            ("◉", "Canlı chat, hediye, beğeni ve takip verileri"),
            ("◈", "OBS Browser Source / widget sistemi"),
            ("✦", "Kişisel tema ve yayıncı ayarları"),
            ("⌁", "Hesaba özel yerel veri ve raporlar"),
        ]:
            row = QHBoxLayout()
            badge = QLabel(icon)
            badge.setFixedWidth(24)
            badge.setStyleSheet("color:#7fb6ff;font-size:18px;font-weight:800")
            lab = QLabel(text)
            lab.setWordWrap(True)
            lab.setStyleSheet("color:#c8d5e7;font-size:13px")
            row.addWidget(badge, 0, Qt.AlignTop)
            row.addWidget(lab, 1)
            brand_layout.addLayout(row)
        brand_layout.addStretch()
        foot = QLabel("Global RπM hesabı • Supabase Auth • Ayarlar bulutta senkronize edilir")
        foot.setObjectName("hint")
        foot.setWordWrap(True)
        brand_layout.addWidget(foot)

        card = QFrame()
        card.setObjectName("authCard")
        shadow = QGraphicsDropShadowEffect(card)
        shadow.setBlurRadius(42)
        shadow.setOffset(0, 12)
        shadow.setColor(QColor(0, 0, 0, 110))
        card.setGraphicsEffect(shadow)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(38, 34, 38, 34)
        card_layout.setSpacing(12)

        switch_row = QHBoxLayout()
        switch_row.setSpacing(8)
        self.login_switch = QPushButton('Giriş Yap')
        self.login_switch.setObjectName('segment')
        self.login_switch.setCheckable(True)
        self.login_switch.clicked.connect(lambda: self.show_register(False))
        self.register_switch = QPushButton('Kayıt Ol')
        self.register_switch.setObjectName('segment')
        self.register_switch.setCheckable(True)
        self.register_switch.clicked.connect(lambda: self.show_register(True))
        switch_row.addWidget(self.login_switch)
        switch_row.addWidget(self.register_switch)
        card_layout.addLayout(switch_row)

        self.stack = QStackedWidget()
        self.login_page = self._login_page()
        self.register_page = self._register_page()
        self.stack.addWidget(self.login_page)
        self.stack.addWidget(self.register_page)
        card_layout.addWidget(self.stack)

        root.addWidget(brand, 5)
        root.addWidget(card, 6)

    def _field(self, placeholder, password=False):
        edit = QLineEdit()
        edit.setPlaceholderText(placeholder)
        if password:
            edit.setEchoMode(QLineEdit.Password)
        return edit

    def _social_buttons(self, lay):
        sep = QHBoxLayout()
        left = QFrame(); left.setFrameShape(QFrame.HLine); left.setStyleSheet('color:#26364b')
        right = QFrame(); right.setFrameShape(QFrame.HLine); right.setStyleSheet('color:#26364b')
        or_label = QLabel('veya')
        or_label.setStyleSheet('color:#7f91aa;padding:0 8px')
        sep.addWidget(left,1); sep.addWidget(or_label); sep.addWidget(right,1)
        lay.addLayout(sep)
        social = QHBoxLayout(); social.setSpacing(9)
        google = QPushButton('G  Google ile devam et')
        google.setObjectName('google')
        google.clicked.connect(lambda: self._start_social('google'))
        social.addWidget(google)
        lay.addLayout(social)
        if not hasattr(self,'social_buttons'):
            self.social_buttons=[]
        self.social_buttons.append(google)

    def _login_page(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)
        title = QLabel("Tekrar hoş geldin")
        title.setObjectName("formTitle")
        sub = QLabel("RπM Studio hesabınla devam et.")
        sub.setObjectName("formSub")
        lay.addWidget(title)
        lay.addWidget(sub)
        lay.addSpacing(12)
        self.login_email = self._field("E-posta adresi")
        self.login_password = self._field("Şifre", True)
        self.login_password.returnPressed.connect(self._do_login)
        self.remember = QCheckBox("Bu cihazda oturumu açık tut")
        self.remember.setChecked(True)
        login = QPushButton("Giriş Yap")
        login.setObjectName("primary")
        login.clicked.connect(self._do_login)
        self.forgot_button = QPushButton("Şifremi unuttum")
        self.forgot_button.setObjectName("secondary")
        self.forgot_button.setToolTip("E-postana şifre sıfırlama bağlantısı gönder")
        self.forgot_button.clicked.connect(self._forgot_password)
        lay.addWidget(self.login_email)
        lay.addWidget(self.login_password)
        lay.addWidget(self.remember)
        lay.addSpacing(4)
        lay.addWidget(login)
        lay.addWidget(self.forgot_button)
        self._social_buttons(lay)
        lay.addStretch()
        hint = QLabel("Hesap RπM Cloud üzerinde tutulur. E-posta doğrulaması açıksa önce gelen doğrulama bağlantısını açman gerekir.")
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        lay.addWidget(hint)
        return page

    def _forgot_password(self):
        email=str(self.login_email.text() or '').strip()
        if not email:
            email, ok = QInputDialog.getText(self, 'Şifremi unuttum', 'RπM Studio hesabındaki e-posta adresi:')
            if not ok:
                return
        try:
            email=self.store.validate_email(email)
        except AuthError as exc:
            QMessageBox.warning(self,'Şifremi unuttum',str(exc))
            return
        self.login_email.setText(email)
        self.forgot_button.setEnabled(False)
        self.forgot_button.setText('E-posta bekleniyor…')

        def worker():
            try:
                state=self.store.recover_password(
                    email,
                    on_sent=lambda value:self.passwordResetSent.emit(str(value)),
                    timeout_seconds=600,
                )
            except Exception as exc:
                self.passwordResetError.emit(str(exc))
                return
            self.passwordResetReady.emit(dict(state))
        threading.Thread(target=worker,daemon=True,name='rpim-password-recovery').start()

    def _password_reset_sent(self, email: str):
        QMessageBox.information(
            self,
            'Şifre sıfırlama e-postası',
            'Eğer bu e-posta RπM Studio hesabına kayıtlıysa şifre sıfırlama bağlantısı gönderildi.\n\n'
            f'E-posta: {email}\n\n'
            'RπM Studio açık kalsın. E-postadaki bağlantıya tıkladıktan sonra uygulama yeni şifreni isteyecek.'
        )

    def _password_reset_error(self, message: str):
        self.forgot_button.setEnabled(True)
        self.forgot_button.setText('Şifremi unuttum')
        QMessageBox.warning(self,'Şifre sıfırlama',str(message or 'Şifre sıfırlama işlemi tamamlanamadı.'))

    def _password_reset_ready(self, recovery_session: dict):
        self.raise_()
        self.activateWindow()
        while True:
            password, ok = QInputDialog.getText(
                self,
                'Yeni şifre',
                'Yeni şifre (en az 8 karakter, büyük/küçük harf, rakam ve sembol):',
                QLineEdit.Password,
            )
            if not ok:
                self.forgot_button.setEnabled(True)
                self.forgot_button.setText('Şifremi unuttum')
                return
            password2, ok2 = QInputDialog.getText(
                self,'Yeni şifre','Yeni şifreyi tekrar gir:',QLineEdit.Password
            )
            if not ok2:
                self.forgot_button.setEnabled(True)
                self.forgot_button.setText('Şifremi unuttum')
                return
            if password != password2:
                QMessageBox.warning(self,'Yeni şifre','Şifreler eşleşmiyor.')
                continue
            try:
                self.store.validate_password(password)
            except AuthError as exc:
                QMessageBox.warning(self,'Yeni şifre',str(exc))
                continue
            try:
                self.store.complete_password_recovery(recovery_session,password)
            except AuthError as exc:
                self._password_reset_error(str(exc))
                return
            break
        self.forgot_button.setEnabled(True)
        self.forgot_button.setText('Şifremi unuttum')
        self.login_password.clear()
        QMessageBox.information(self,'Şifre güncellendi','Şifren başarıyla değiştirildi. Yeni şifrenle giriş yapabilirsin.')

    def _register_page(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(11)
        title = QLabel("RπM Studio hesabı oluştur")
        title.setObjectName("formTitle")
        sub = QLabel("Bir e-posta, tek yayıncı adı ve şifre ile hesabını oluştur. İstersen üstten Giriş Yap sekmesine de geçebilirsin.")
        sub.setObjectName("formSub")
        lay.addWidget(title)
        lay.addWidget(sub)
        lay.addSpacing(8)
        self.reg_email = self._field("E-posta adresi")
        self.reg_publisher = self._field("TikTok yayıncı adı (örn. mertlive)")
        self.reg_password = self._field("Şifre • en az 8 karakter, büyük/küçük harf, rakam ve sembol", True)
        self.reg_password2 = self._field("Şifreyi tekrar gir", True)
        self.local_ack = QCheckBox("RπM Studio hesabımın Supabase üzerinde oluşturulacağını kabul ediyorum")
        create = QPushButton("Hesap Oluştur ve Devam Et")
        create.setObjectName("primary")
        create.clicked.connect(self._do_register)
        back = QPushButton("Zaten hesabım var")
        back.setObjectName("secondary")
        back.clicked.connect(lambda: self.show_register(False))
        lay.addWidget(self.reg_email)
        lay.addWidget(self.reg_publisher)
        lay.addWidget(self.reg_password)
        lay.addWidget(self.reg_password2)
        lay.addWidget(self.local_ack)
        lay.addSpacing(4)
        lay.addWidget(create)
        self._social_buttons(lay)
        lay.addWidget(back)
        lay.addStretch()
        return page

    def _set_social_busy(self, busy: bool, provider: str = ''):
        for button in getattr(self,'social_buttons',[]):
            button.setEnabled(not busy)
        if busy:
            self.setWindowTitle(f"RπM Studio • {provider.title()} ile giriş bekleniyor")

    def _start_social(self, provider: str):
        remember = bool(getattr(self,'remember',None) and self.remember.isChecked())

        # If OAuth is started from the Kayıt Ol page, reuse the publisher name
        # already typed in that form. Previously this field was ignored, which
        # made Google accounts keep the temporary user_<uuid> value.
        self._pending_social_publisher = ""
        try:
            on_register = self.stack.currentWidget() is self.register_page
        except Exception:
            on_register = False
        if on_register:
            typed = str(getattr(self, 'reg_publisher', QLineEdit()).text() or '').strip()
            if typed:
                try:
                    self._pending_social_publisher = self.store.validate_publisher(typed)
                except AuthError as exc:
                    QMessageBox.warning(self, 'TikTok yayıncı adı', str(exc))
                    return

        self._set_social_busy(True, provider)
        def worker():
            try:
                account = self.store.authenticate_oauth(provider, remember=remember)
            except Exception as exc:
                self.socialError.emit(str(exc))
                return
            self.socialSuccess.emit(dict(account))
        threading.Thread(target=worker, daemon=True, name=f'rpim-oauth-{provider}').start()

    def _social_error(self, message: str):
        self._set_social_busy(False)
        self.setWindowTitle('RπM Studio • Giriş')
        msg = str(message or 'Sosyal giriş başarısız oldu.')
        if 'provider is not enabled' in msg.lower() or 'unsupported provider' in msg.lower():
            msg += '\n\nSupabase Dashboard > Authentication > Sign In / Providers bölümünden bu sağlayıcıyı etkinleştirmen gerekir.'
        QMessageBox.warning(self,'Sosyal giriş',msg)

    def _social_success(self, account: dict):
        self._set_social_busy(False)
        account=dict(account or {})

        # Bring the app back to the foreground after the browser OAuth flow so
        # first-login onboarding cannot appear hidden behind Chrome/Opera.
        self.show()
        self.raise_()
        self.activateWindow()

        needs_publisher = bool(account.get('needs_publisher'))
        current = str(account.get('publisher_username') or '').strip().lower()
        if not current or current.startswith('user_'):
            needs_publisher = True

        # Kayıt Ol sayfasında önceden yazılmış isim varsa otomatik kaydet.
        pending = str(getattr(self, '_pending_social_publisher', '') or '').strip()
        if needs_publisher and pending:
            try:
                account = self.store.update_publisher(account.get('id'), pending)
                needs_publisher = False
            except AuthError as exc:
                QMessageBox.warning(self, 'Yayıncı adı', str(exc))

        # Giriş Yap ekranından ilk kez sosyal hesap kullanıldıysa isim zorunlu
        # onboarding penceresiyle istenir; isim kaydedilmeden ana ekran açılmaz.
        if needs_publisher:
            while True:
                value, ok = QInputDialog.getText(
                    self,
                    'TikTok yayıncı adını tamamla',
                    'Google hesabın bağlandı.\nRπM Studio için kullanacağın TikTok yayıncı adını gir:',
                    QLineEdit.Normal,
                    '',
                )
                if not ok:
                    try:
                        self.store.clear_local_session(account.get('id'))
                    except Exception:
                        pass
                    self._pending_social_publisher = ''
                    self.setWindowTitle('RπM Studio • Giriş')
                    return
                try:
                    account = self.store.update_publisher(account.get('id'), value)
                    break
                except AuthError as exc:
                    QMessageBox.warning(self, 'Yayıncı adı', str(exc))

        self._pending_social_publisher = ''
        self.account=dict(account)
        self.accept()

    def show_register(self, register: bool):
        self.stack.setCurrentWidget(self.register_page if register else self.login_page)
        self.setWindowTitle("RπM Studio • Kayıt" if register else "RπM Studio • Giriş")
        try:
            self.register_switch.setChecked(bool(register))
            self.login_switch.setChecked(not bool(register))
        except Exception:
            pass

    def _do_login(self):
        try:
            account = self.store.authenticate(
                self.login_email.text(), self.login_password.text(), self.remember.isChecked()
            )
        except AuthError as exc:
            QMessageBox.warning(self, "Giriş yapılamadı", str(exc))
            return
        self.account = account
        self.accept()

    def _do_register(self):
        if self.reg_password.text() != self.reg_password2.text():
            QMessageBox.warning(self, "Kayıt", "Şifreler eşleşmiyor.")
            return
        if not self.local_ack.isChecked():
            QMessageBox.warning(self, "Kayıt", "RπM Cloud hesap bilgisini onaylayın.")
            return
        try:
            account = self.store.create_account(
                self.reg_email.text(), self.reg_publisher.text(), self.reg_password.text()
            )
        except AuthError as exc:
            QMessageBox.warning(self, "Kayıt yapılamadı", str(exc))
            return
        if account.get("pending_verification"):
            self.login_email.setText(str(account.get("email") or ""))
            self.login_password.clear()
            self.show_register(False)
            QMessageBox.information(
                self,
                "E-posta doğrulaması",
                "Hesabın oluşturuldu. E-posta doğrulaması açıksa gelen bağlantıyı aç, ardından Giriş Yap bölümünden devam et.",
            )
            return
        self.store.create_remember_session(account["id"])
        self.account = account
        QMessageBox.information(self, "RπM Studio", "Global hesabın oluşturuldu. Hoş geldin!")
        self.accept()


class AccountDialog(QDialog):
    accountUpdated = Signal(dict)
    logoutRequested = Signal()

    def __init__(self, store: AccountStore, account: dict, parent=None):
        super().__init__(parent)
        self.store = store
        self.account = dict(account)
        self.setWindowTitle("RπM Studio • Hesap")
        self.resize(520, 500)
        self.setMinimumSize(500, 460)
        self.setStyleSheet(AUTH_QSS)
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(12)

        title = QLabel("Hesabım")
        title.setObjectName("formTitle")
        root.addWidget(title)
        mail = QLabel(self.account.get("email", ""))
        mail.setObjectName("formSub")
        root.addWidget(mail)

        root.addSpacing(10)
        root.addWidget(QLabel("Yayıncı adı"))
        self.publisher = QLineEdit(self.account.get("publisher_username", ""))
        root.addWidget(self.publisher)
        save = QPushButton("Yayıncı Adını Kaydet")
        save.setObjectName("primary")
        save.clicked.connect(self._save_publisher)
        root.addWidget(save)

        root.addSpacing(14)
        root.addWidget(QLabel("Şifre değiştir"))
        self.current_password = self._password("Mevcut şifre")
        self.new_password = self._password("Yeni şifre • en az 8 karakter, büyük/küçük harf, rakam ve sembol")
        self.new_password2 = self._password("Yeni şifreyi tekrar gir")
        root.addWidget(self.current_password)
        root.addWidget(self.new_password)
        root.addWidget(self.new_password2)
        change = QPushButton("Şifreyi Değiştir")
        change.setObjectName("secondary")
        change.clicked.connect(self._change_password)
        root.addWidget(change)
        root.addStretch()
        logout = QPushButton("Oturumu Kapat")
        logout.setObjectName("secondary")
        logout.setStyleSheet("QPushButton{color:#ff9a9a;border-color:rgba(255,90,90,.25)}")
        logout.clicked.connect(self._logout)
        root.addWidget(logout)

    @staticmethod
    def _password(placeholder):
        e = QLineEdit()
        e.setPlaceholderText(placeholder)
        e.setEchoMode(QLineEdit.Password)
        return e

    def _save_publisher(self):
        try:
            self.account = self.store.update_publisher(self.account["id"], self.publisher.text())
        except AuthError as exc:
            QMessageBox.warning(self, "Hesap", str(exc))
            return
        self.accountUpdated.emit(dict(self.account))
        QMessageBox.information(self, "Hesap", "Yayıncı adı güncellendi.")

    def _change_password(self):
        if self.new_password.text() != self.new_password2.text():
            QMessageBox.warning(self, "Şifre", "Yeni şifreler eşleşmiyor.")
            return
        try:
            self.store.change_password(self.account["id"], self.current_password.text(), self.new_password.text())
        except AuthError as exc:
            QMessageBox.warning(self, "Şifre", str(exc))
            return
        self.current_password.clear()
        self.new_password.clear()
        self.new_password2.clear()
        QMessageBox.information(self, "Şifre", "Şifre güncellendi. Güvenlik için hatırlanan oturum kapatıldı.")

    def _logout(self):
        answer = QMessageBox.question(self, "Oturumu kapat", "RπM Studio hesabından çıkış yapılsın mı?")
        if answer == QMessageBox.Yes:
            self.logoutRequested.emit()
            self.accept()
