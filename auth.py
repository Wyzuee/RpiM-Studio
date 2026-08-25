from __future__ import annotations

import base64
import json
import os
import re
import threading
import hashlib
import secrets
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, urlparse
from pathlib import Path
from typing import Any

import requests

from app_paths import app_data_root
from cloud_config import SUPABASE_PUBLISHABLE_KEY, SUPABASE_URL

EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
PUBLISHER_RE = re.compile(r"^[A-Za-z0-9._]{2,24}$")
OAUTH_CALLBACK_HOST = "127.0.0.1"
OAUTH_CALLBACK_PORT = 8766
OAUTH_TIMEOUT_SECONDS = 180


class AuthError(ValueError):
    pass


class AccountStore:
    """Global RπM Studio account store backed by Supabase Auth + PostgREST.

    Only Supabase's publishable client key ships in the desktop app. Passwords
    never pass through RπM-owned storage; they are sent directly over HTTPS to
    Supabase Auth. The optional remember-me refresh token is protected with
    Windows DPAPI when available.
    """

    def __init__(self, root: Path | None = None):
        self.root = Path(root) if root else app_data_root()
        self.root.mkdir(parents=True, exist_ok=True)
        self.session_path = self.root / "cloud_session.json"
        self.lock = threading.RLock()
        self.http = requests.Session()
        self.url = SUPABASE_URL
        self.key = SUPABASE_PUBLISHABLE_KEY
        self._session: dict[str, Any] = {}
        self._account: dict[str, Any] | None = None

    @staticmethod
    def normalize_email(email: str) -> str:
        return str(email or "").strip().casefold()

    @staticmethod
    def normalize_publisher(username: str) -> str:
        return str(username or "").strip().lstrip("@").casefold()

    @staticmethod
    def validate_email(email: str) -> str:
        value = AccountStore.normalize_email(email)
        if not EMAIL_RE.fullmatch(value):
            raise AuthError("Geçerli bir e-posta adresi girin.")
        return value

    @staticmethod
    def validate_publisher(username: str) -> str:
        value = AccountStore.normalize_publisher(username)
        if not PUBLISHER_RE.fullmatch(value):
            raise AuthError("Yayıncı adı 2-24 karakter olmalı; sadece harf, sayı, nokta ve alt çizgi kullanın.")
        return value

    @staticmethod
    def validate_password(password: str) -> str:
        value = str(password or "")
        if len(value) < 8:
            raise AuthError("Şifre en az 8 karakter olmalı.")
        if len(value) > 128:
            raise AuthError("Şifre en fazla 128 karakter olabilir.")
        if not re.search(r"[a-z]", value):
            raise AuthError("Şifrede en az bir küçük harf olmalı.")
        if not re.search(r"[A-Z]", value):
            raise AuthError("Şifrede en az bir büyük harf olmalı.")
        if not re.search(r"\d", value):
            raise AuthError("Şifrede en az bir rakam olmalı.")
        if not re.search(r"[^A-Za-z0-9]", value):
            raise AuthError("Şifrede en az bir sembol olmalı.")
        return value

    def has_accounts(self) -> bool:
        # A global account may exist even if this PC has never signed in before.
        return True

    def _headers(self, access_token: str | None = None, prefer: str | None = None) -> dict[str, str]:
        headers = {
            "apikey": self.key,
            "Authorization": f"Bearer {access_token or self.key}",
            "Content-Type": "application/json",
        }
        if prefer:
            headers["Prefer"] = prefer
        return headers

    @staticmethod
    def _message(data: Any, status: int) -> str:
        if isinstance(data, dict):
            msg = data.get("msg") or data.get("message") or data.get("error_description") or data.get("error") or data.get("hint")
            if msg:
                msg = str(msg)
                low = msg.lower()
                if "invalid login credentials" in low:
                    return "E-posta veya şifre hatalı."
                if "email not confirmed" in low:
                    return "E-posta adresi henüz doğrulanmamış. E-postandaki doğrulama bağlantısını açıp tekrar giriş yap."
                if "user already registered" in low or "already been registered" in low:
                    return "Bu e-posta adresi zaten kayıtlı. Giriş Yap bölümünü kullan."
                if "duplicate key" in low or "profiles_publisher_username_unique" in low:
                    return "Bu TikTok yayıncı adı başka bir RπM Studio hesabında kullanılıyor."
                if "password" in low and ("weak" in low or "characters" in low):
                    return "Şifre Supabase güvenlik kurallarını karşılamıyor."
                return msg
        return f"Sunucu isteği başarısız oldu (HTTP {status})."

    def _request(
        self,
        method: str,
        path: str,
        *,
        access_token: str | None = None,
        payload: dict | None = None,
        params: dict | None = None,
        prefer: str | None = None,
        timeout: float = 15.0,
    ) -> tuple[Any, requests.Response]:
        try:
            response = self.http.request(
                method,
                self.url + path,
                headers=self._headers(access_token, prefer),
                json=payload,
                params=params,
                timeout=timeout,
            )
        except requests.RequestException as exc:
            raise AuthError("RπM Cloud'a bağlanılamadı. İnternet bağlantını kontrol et.") from exc
        try:
            data = response.json() if response.content else None
        except ValueError:
            data = response.text
        if not (200 <= response.status_code < 300):
            raise AuthError(self._message(data, response.status_code))
        return data, response

    @staticmethod
    def _protect(value: str) -> dict:
        raw = value.encode("utf-8")
        if os.name == "nt":
            try:
                import win32crypt
                encrypted = win32crypt.CryptProtectData(raw, "RpiM Studio", None, None, None, 0)
                return {"scheme": "dpapi", "value": base64.b64encode(encrypted).decode("ascii")}
            except Exception:
                pass
        return {"scheme": "base64", "value": base64.b64encode(raw).decode("ascii")}

    @staticmethod
    def _unprotect(blob: dict) -> str:
        data = base64.b64decode(str(blob.get("value") or ""))
        if blob.get("scheme") == "dpapi" and os.name == "nt":
            import win32crypt
            return win32crypt.CryptUnprotectData(data, None, None, None, 0)[1].decode("utf-8")
        return data.decode("utf-8")

    def _save_remember_token(self, refresh_token: str, account_id: str) -> None:
        tmp = self.session_path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps({"account_id": str(account_id), "refresh_token": self._protect(refresh_token)}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp.replace(self.session_path)

    def _set_session(self, data: dict, remember: bool = False) -> None:
        self._session = {
            "access_token": str(data.get("access_token") or ""),
            "refresh_token": str(data.get("refresh_token") or ""),
            "expires_in": data.get("expires_in"),
            "token_type": data.get("token_type"),
        }
        if remember and self._session["refresh_token"]:
            user = data.get("user") or {}
            user_id = str(user.get("id") or self._account_id_from_token_fallback())
            if user_id:
                self._save_remember_token(self._session["refresh_token"], user_id)

    def _account_id_from_token_fallback(self) -> str:
        return str((self._account or {}).get("id") or "")

    @property
    def access_token(self) -> str:
        token = str(self._session.get("access_token") or "")
        if not token:
            raise AuthError("Oturum bulunamadı. Lütfen tekrar giriş yap.")
        return token

    def _fetch_profile(self, user: dict | None = None) -> dict:
        user = dict(user or {})
        user_id = str(user.get("id") or "")
        if not user_id:
            u, _ = self._request("GET", "/auth/v1/user", access_token=self.access_token)
            user = dict(u or {})
            user_id = str(user.get("id") or "")
        rows, _ = self._request(
            "GET",
            "/rest/v1/profiles",
            access_token=self.access_token,
            params={"user_id": f"eq.{user_id}", "select": "user_id,publisher_username,display_name,created_at,updated_at"},
        )
        profile = rows[0] if isinstance(rows, list) and rows else {}
        meta = user.get("user_metadata") or user.get("raw_user_meta_data") or {}
        account = {
            "id": user_id,
            "email": str(user.get("email") or ""),
            "publisher_username": str(profile.get("publisher_username") or meta.get("publisher_username") or ""),
            "display_name": str(profile.get("display_name") or meta.get("display_name") or ""),
            "created_at": str(profile.get("created_at") or user.get("created_at") or ""),
            "updated_at": str(profile.get("updated_at") or ""),
            "cloud": True,
        }
        self._account = account
        return dict(account)

    @staticmethod
    def _pkce_pair() -> tuple[str, str]:
        verifier = secrets.token_urlsafe(64)[:96]
        challenge = base64.urlsafe_b64encode(
            hashlib.sha256(verifier.encode("ascii")).digest()
        ).decode("ascii").rstrip("=")
        return verifier, challenge

    def authenticate_oauth(self, provider: str, remember: bool = True) -> dict:
        """Authenticate with Google through Supabase OAuth + PKCE.

        A short-lived localhost callback is used because RπM Studio is a Windows
        desktop app. Supabase must allow the callback pattern
        http://127.0.0.1:8766/auth/callback/** in Authentication > URL Configuration.
        """
        provider = str(provider or "").strip().lower()
        if provider != "google":
            raise AuthError("Desteklenmeyen sosyal giriş sağlayıcısı.")

        verifier, challenge = self._pkce_pair()
        state = secrets.token_urlsafe(24)
        callback_path = f"/auth/callback/{state}"
        redirect_to = f"http://{OAUTH_CALLBACK_HOST}:{OAUTH_CALLBACK_PORT}{callback_path}"
        result: dict[str, str] = {}

        class CallbackServer(ThreadingHTTPServer):
            allow_reuse_address = True
            daemon_threads = True

        class CallbackHandler(BaseHTTPRequestHandler):
            def log_message(self, format, *args):
                return

            def do_GET(inner_self):
                parsed = urlparse(inner_self.path)
                if parsed.path != callback_path:
                    inner_self.send_response(404)
                    inner_self.end_headers()
                    return
                params = parse_qs(parsed.query)
                if params.get("code"):
                    result["code"] = str(params["code"][0])
                if params.get("error"):
                    result["error"] = str(params["error"][0])
                if params.get("error_description"):
                    result["error_description"] = str(params["error_description"][0])
                body = (
                    "<!doctype html><html><head><meta charset='utf-8'><title>RπM Studio</title>"
                    "<style>body{font-family:Segoe UI,Arial;background:#0b1220;color:#eef5ff;"
                    "display:grid;place-items:center;height:100vh;margin:0}.card{background:#111b2b;"
                    "padding:32px;border-radius:18px;border:1px solid #29405f;text-align:center}"
                    "h1{margin:0 0 10px}p{color:#aabbd1}</style></head><body><div class='card'>"
                    "<h1>RπM Studio</h1><p>Giriş tamamlandı. Bu sekmeyi kapatıp uygulamaya dönebilirsin.</p>"
                    "</div></body></html>"
                ).encode("utf-8")
                inner_self.send_response(200)
                inner_self.send_header("Content-Type", "text/html; charset=utf-8")
                inner_self.send_header("Content-Length", str(len(body)))
                inner_self.end_headers()
                inner_self.wfile.write(body)

        try:
            server = CallbackServer((OAUTH_CALLBACK_HOST, OAUTH_CALLBACK_PORT), CallbackHandler)
        except OSError as exc:
            raise AuthError(
                f"Sosyal giriş callback portu ({OAUTH_CALLBACK_PORT}) kullanılamıyor. "
                "RπM Studio'nun başka bir kopyasını kapatıp tekrar dene."
            ) from exc

        query = (
            f"provider={quote(provider)}"
            f"&redirect_to={quote(redirect_to, safe='')}"
            f"&code_challenge={quote(challenge)}"
            "&code_challenge_method=s256"
        )
        authorize_url = f"{self.url}/auth/v1/authorize?{query}"
        server.timeout = 1.0
        try:
            if not webbrowser.open(authorize_url, new=1, autoraise=True):
                raise AuthError("Varsayılan tarayıcı açılamadı. OAuth bağlantısını başlatamadım.")
            deadline = time.monotonic() + OAUTH_TIMEOUT_SECONDS
            while time.monotonic() < deadline and not result:
                server.handle_request()
        finally:
            try:
                server.server_close()
            except Exception:
                pass

        if not result:
            raise AuthError("Sosyal giriş zaman aşımına uğradı. Tekrar deneyebilirsin.")
        if result.get("error"):
            detail = result.get("error_description") or result.get("error") or "OAuth giriş hatası"
            raise AuthError(str(detail))
        code = str(result.get("code") or "")
        if not code:
            raise AuthError("Sosyal giriş kodu alınamadı.")

        data, _ = self._request(
            "POST",
            "/auth/v1/token",
            params={"grant_type": "pkce"},
            payload={"auth_code": code, "code_verifier": verifier},
        )
        if not isinstance(data, dict) or not data.get("access_token"):
            raise AuthError("Sosyal giriş oturumu oluşturulamadı.")
        self._set_session(data, remember=remember)
        if not remember:
            self._remove_session_file()
        account = self._fetch_profile(data.get("user") or {})
        publisher = str(account.get("publisher_username") or "")
        account["oauth_provider"] = provider
        account["needs_publisher"] = (not publisher) or publisher.startswith("user_")
        self._account = dict(account)
        return dict(account)

    def create_account(self, email: str, publisher_username: str, password: str) -> dict:
        email = self.validate_email(email)
        publisher = self.validate_publisher(publisher_username)
        password = self.validate_password(password)
        data, _ = self._request(
            "POST",
            "/auth/v1/signup",
            payload={
                "email": email,
                "password": password,
                "data": {"publisher_username": publisher, "display_name": publisher},
            },
        )
        if not isinstance(data, dict):
            raise AuthError("Kayıt yanıtı okunamadı.")
        if not data.get("access_token"):
            return {
                "pending_verification": True,
                "email": email,
                "publisher_username": publisher,
                "id": str((data.get("user") or {}).get("id") or ""),
            }
        self._set_session(data, remember=True)
        return self._fetch_profile(data.get("user") or {})

    def authenticate(self, email: str, password: str, remember: bool = False) -> dict:
        email = self.validate_email(email)
        data, _ = self._request(
            "POST",
            "/auth/v1/token",
            params={"grant_type": "password"},
            payload={"email": email, "password": str(password or "")},
        )
        if not isinstance(data, dict) or not data.get("access_token"):
            raise AuthError("Giriş yanıtı geçersiz.")
        self._set_session(data, remember=remember)
        if not remember:
            self._remove_session_file()
        return self._fetch_profile(data.get("user") or {})

    def recover_password(self, email: str, on_sent=None, timeout_seconds: int = 600) -> dict:
        """Send a Supabase recovery email and wait for the desktop PKCE callback.

        Uses the same localhost:8766 callback wildcard as Google OAuth.
        RπM Studio must stay open while the user clicks the email link.
        """
        email = self.validate_email(email)
        verifier, challenge = self._pkce_pair()
        state = secrets.token_urlsafe(24)
        callback_path = f"/auth/callback/recovery/{state}"
        redirect_to = f"http://{OAUTH_CALLBACK_HOST}:{OAUTH_CALLBACK_PORT}{callback_path}"
        result: dict[str, str] = {}

        class CallbackServer(ThreadingHTTPServer):
            allow_reuse_address = True
            daemon_threads = True

        class RecoveryHandler(BaseHTTPRequestHandler):
            def log_message(inner_self, format, *args):
                return

            def do_GET(inner_self):
                parsed = urlparse(inner_self.path)
                if parsed.path != callback_path:
                    inner_self.send_response(404)
                    inner_self.end_headers()
                    return
                params = parse_qs(parsed.query)
                if params.get("code"):
                    result["code"] = str(params["code"][0])
                if params.get("error"):
                    result["error"] = str(params["error"][0])
                if params.get("error_description"):
                    result["error_description"] = str(params["error_description"][0])
                body = (
                    "<!doctype html><html><head><meta charset='utf-8'><title>RπM Studio</title>"
                    "<style>body{font-family:Segoe UI,Arial;background:#0b1220;color:#eef5ff;"
                    "display:grid;place-items:center;height:100vh;margin:0}.card{background:#111b2b;"
                    "padding:34px;border-radius:18px;border:1px solid #29405f;text-align:center;max-width:520px}"
                    "h1{margin:0 0 10px}p{color:#aabbd1;line-height:1.5}</style></head><body><div class='card'>"
                    "<h1>RπM Studio</h1><p>Şifre sıfırlama bağlantısı doğrulandı. "
                    "RπM Studio'ya dönüp yeni şifreni belirleyebilirsin.</p></div></body></html>"
                ).encode("utf-8")
                inner_self.send_response(200)
                inner_self.send_header("Content-Type", "text/html; charset=utf-8")
                inner_self.send_header("Content-Length", str(len(body)))
                inner_self.end_headers()
                inner_self.wfile.write(body)

        try:
            server = CallbackServer((OAUTH_CALLBACK_HOST, OAUTH_CALLBACK_PORT), RecoveryHandler)
        except OSError as exc:
            raise AuthError(
                f"Şifre sıfırlama callback portu ({OAUTH_CALLBACK_PORT}) kullanılamıyor. "
                "RπM Studio'nun başka bir kopyasını kapatıp tekrar dene."
            ) from exc

        try:
            self._request(
                "POST",
                "/auth/v1/recover",
                params={"redirect_to": redirect_to},
                payload={
                    "email": email,
                    "code_challenge": challenge,
                    "code_challenge_method": "s256",
                },
            )
            if callable(on_sent):
                try:
                    on_sent(email)
                except Exception:
                    pass

            server.timeout = 1.0
            deadline = time.monotonic() + max(60, int(timeout_seconds))
            while time.monotonic() < deadline and not result:
                server.handle_request()
        finally:
            try:
                server.server_close()
            except Exception:
                pass

        if not result:
            raise AuthError("Şifre sıfırlama bağlantısı için bekleme süresi doldu. Tekrar deneyebilirsin.")
        if result.get("error"):
            detail = result.get("error_description") or result.get("error") or "Şifre sıfırlama bağlantısı geçersiz."
            raise AuthError(str(detail))
        code = str(result.get("code") or "")
        if not code:
            raise AuthError("Şifre sıfırlama doğrulama kodu alınamadı.")

        data, _ = self._request(
            "POST",
            "/auth/v1/token",
            params={"grant_type": "pkce"},
            payload={"auth_code": code, "code_verifier": verifier},
        )
        if not isinstance(data, dict) or not data.get("access_token"):
            raise AuthError("Şifre sıfırlama oturumu oluşturulamadı.")
        return {
            "access_token": str(data.get("access_token") or ""),
            "refresh_token": str(data.get("refresh_token") or ""),
            "email": email,
            "user": dict(data.get("user") or {}),
        }

    def complete_password_recovery(self, recovery_session: dict, new_password: str) -> None:
        new_password = self.validate_password(new_password)
        access_token = str((recovery_session or {}).get("access_token") or "")
        if not access_token:
            raise AuthError("Şifre sıfırlama oturumu bulunamadı. İşlemi yeniden başlat.")
        self._request(
            "PUT",
            "/auth/v1/user",
            access_token=access_token,
            payload={"password": new_password},
        )
        try:
            self._request("POST", "/auth/v1/logout", access_token=access_token, timeout=6)
        except Exception:
            pass
        self._session = {}
        self._account = None
        self._remove_session_file()

    def create_remember_session(self, account_id: str) -> None:
        refresh = str(self._session.get("refresh_token") or "")
        if refresh:
            self._save_remember_token(refresh, str(account_id))

    def try_auto_login(self) -> dict | None:
        try:
            raw = json.loads(self.session_path.read_text(encoding="utf-8"))
            refresh_token = self._unprotect(dict(raw.get("refresh_token") or {}))
            if not refresh_token:
                return None
            data, _ = self._request(
                "POST",
                "/auth/v1/token",
                params={"grant_type": "refresh_token"},
                payload={"refresh_token": refresh_token},
            )
            if not isinstance(data, dict) or not data.get("access_token"):
                self._remove_session_file()
                return None
            self._set_session(data, remember=True)
            return self._fetch_profile(data.get("user") or {})
        except Exception:
            return None

    def _remove_session_file(self) -> None:
        try:
            self.session_path.unlink()
        except FileNotFoundError:
            pass
        except OSError:
            pass

    def clear_local_session(self, account_id: str | None = None, clear_db_token: bool = True) -> None:
        token = str(self._session.get("access_token") or "")
        if token:
            try:
                self._request("POST", "/auth/v1/logout", access_token=token, timeout=6)
            except Exception:
                pass
        self._session = {}
        self._account = None
        self._remove_session_file()

    def update_publisher(self, account_id: str, username: str) -> dict:
        """Persist the single TikTok publisher name for the signed-in account.

        Social OAuth users are initially created by the Supabase trigger with a
        temporary ``user_<uuid>`` publisher name.  We update both the public
        profile row and Auth user metadata so the value survives future profile
        rebuilds and is available consistently on every device.
        """
        publisher = self.validate_publisher(username)
        account_id = str(account_id or (self._account or {}).get("id") or "").strip()
        if not account_id:
            raise AuthError("Hesap kimliği bulunamadı. Lütfen tekrar giriş yap.")

        rows, _ = self._request(
            "PATCH",
            "/rest/v1/profiles",
            access_token=self.access_token,
            params={"user_id": f"eq.{account_id}"},
            payload={"publisher_username": publisher, "display_name": publisher},
            prefer="return=representation",
        )

        # Keep Supabase Auth metadata in sync as a second source of truth.
        try:
            self._request(
                "PUT",
                "/auth/v1/user",
                access_token=self.access_token,
                payload={"data": {"publisher_username": publisher, "display_name": publisher}},
            )
        except Exception:
            # The public profile is authoritative for RπM Studio. Metadata sync
            # failure must not undo a successful profile update.
            pass

        refreshed = self._fetch_profile()
        saved = self.normalize_publisher(refreshed.get("publisher_username") or "")
        if saved != publisher:
            raise AuthError(
                "TikTok yayıncı adı Supabase profiline kaydedilemedi. "
                "profiles tablosundaki RLS/update policy ayarını kontrol edin."
            )
        refreshed["needs_publisher"] = False
        return refreshed

    def change_password(self, account_id: str, current_password: str, new_password: str) -> None:
        new_password = self.validate_password(new_password)
        email = str((self._account or {}).get("email") or "")
        if not email:
            raise AuthError("Hesap e-posta bilgisi bulunamadı.")
        verify, _ = self._request(
            "POST",
            "/auth/v1/token",
            params={"grant_type": "password"},
            payload={"email": email, "password": str(current_password or "")},
        )
        temp_access = str((verify or {}).get("access_token") or "")
        if not temp_access:
            raise AuthError("Mevcut şifre doğrulanamadı.")
        self._request("PUT", "/auth/v1/user", access_token=temp_access, payload={"password": new_password})
        # Refresh the in-memory session with the new password, but do not persist it automatically.
        fresh, _ = self._request(
            "POST",
            "/auth/v1/token",
            params={"grant_type": "password"},
            payload={"email": email, "password": new_password},
        )
        if isinstance(fresh, dict) and fresh.get("access_token"):
            self._set_session(fresh, remember=False)
        self._remove_session_file()

    def get_account(self, account_id: str) -> dict | None:
        if self._account and str(self._account.get("id")) == str(account_id):
            return dict(self._account)
        try:
            return self._fetch_profile()
        except AuthError:
            return None

    def get_cloud_settings(self) -> dict:
        account_id = str((self._account or {}).get("id") or "")
        if not account_id:
            return {}
        rows, _ = self._request(
            "GET",
            "/rest/v1/user_settings",
            access_token=self.access_token,
            params={"user_id": f"eq.{account_id}", "select": "settings"},
        )
        if isinstance(rows, list) and rows and isinstance(rows[0].get("settings"), dict):
            return dict(rows[0]["settings"])
        return {}

    def save_cloud_settings(self, settings: dict) -> None:
        account_id = str((self._account or {}).get("id") or "")
        if not account_id:
            return
        try:
            self._request(
                "PATCH",
                "/rest/v1/user_settings",
                access_token=self.access_token,
                params={"user_id": f"eq.{account_id}"},
                payload={"settings": dict(settings or {})},
                prefer="return=minimal",
            )
        except AuthError:
            # Trigger normally creates the row. This fallback covers old/manual accounts.
            self._request(
                "POST",
                "/rest/v1/user_settings",
                access_token=self.access_token,
                payload={"user_id": account_id, "settings": dict(settings or {})},
                prefer="resolution=merge-duplicates,return=minimal",
            )

    def close(self) -> None:
        try:
            self.http.close()
        except Exception:
            pass
