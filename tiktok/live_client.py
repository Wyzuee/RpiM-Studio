import asyncio
import json
import threading
from urllib.parse import urlencode


EULER_WS_BASE = "wss://ws.eulerstream.com"


CLOSE_MESSAGES = {
    4005: "Yayın sona erdi.",
    4006: "Euler WebSocket uzun süre veri alamadığı için kapandı.",
    4400: "Euler WebSocket seçenekleri geçersiz.",
    4401: "Euler API anahtarı geçersiz veya yetkilendirme başarısız.",
    4403: "Euler hesabının bu WebSocket bağlantısı için izni yok.",
    4404: "Kullanıcı şu anda LIVE değil veya yayın bulunamadı.",
    4429: "Euler hesabında eşzamanlı bağlantı limiti aşıldı.",
    4500: "TikTok uzak WebSocket bağlantısını kapattı.",
    4555: "Euler WebSocket maksimum bağlantı ömrüne ulaştı.",
    4556: "Euler TikTok webcast verisini alamadı.",
    4557: "Euler yayın oda bilgisini alamadı.",
}


def build_euler_ws_url(username, api_key):
    """Build the managed Euler Stream WebSocket URL without logging the secret."""
    params = {
        "uniqueId": str(username or "").strip().lstrip("@"),
        "apiKey": str(api_key or "").strip(),
        # Ask Euler to return decoded JSON events rather than raw protobuf frames.
        "features.bundleEvents": "true",
        "features.rawMessages": "false",
        "features.normalizeUniqueId": "true",
        "features.syntheticPresence": "true",
        "features.schemaVersion": "v2",
    }
    return EULER_WS_BASE + "?" + urlencode(params)


def _as_dict(value):
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def _ci_get(mapping, *names, default=None):
    if not isinstance(mapping, dict):
        return default
    for name in names:
        if name in mapping:
            return mapping[name]
    lower = {str(k).casefold(): v for k, v in mapping.items()}
    for name in names:
        key = str(name).casefold()
        if key in lower:
            return lower[key]
    return default


def _to_int(value, default=0):
    try:
        if isinstance(value, bool):
            return int(value)
        return int(value or 0)
    except (TypeError, ValueError):
        return default


def _find_first(obj, names, depth=0):
    """Find a key in a JSON-like structure while keeping recursion bounded."""
    if depth > 5:
        return None
    if isinstance(obj, dict):
        value = _ci_get(obj, *names, default=None)
        if value is not None:
            return value
        for child in obj.values():
            if isinstance(child, (dict, list)):
                value = _find_first(child, names, depth + 1)
                if value is not None:
                    return value
    elif isinstance(obj, list):
        for child in obj:
            value = _find_first(child, names, depth + 1)
            if value is not None:
                return value
    return None


def _image_url(obj):
    if not obj:
        return ""
    if isinstance(obj, str):
        return obj if obj.startswith(("http://", "https://")) else ""
    if isinstance(obj, list):
        for x in obj:
            url = _image_url(x)
            if url:
                return url
        return ""
    if isinstance(obj, dict):
        for key in ("url", "uri"):
            value = _ci_get(obj, key)
            if isinstance(value, str) and value.startswith(("http://", "https://")):
                return value
        for key in ("urls", "urlList", "url_list"):
            value = _ci_get(obj, key)
            url = _image_url(value)
            if url:
                return url
        for value in obj.values():
            if isinstance(value, (dict, list)):
                url = _image_url(value)
                if url:
                    return url
    return ""


def _user_info(payload):
    user = _find_first(payload, ("user", "fromUser", "from_user"))
    user = user if isinstance(user, dict) else {}

    username = _ci_get(user, "uniqueId", "unique_id", "displayId", "display_id", "username", "userName", "user_name", default="")
    nickname = _ci_get(user, "nickname", "nickName", "displayName", "display_name", "name", default="")

    # Some normalized messages flatten user fields onto the event object.
    if not username:
        username = _ci_get(payload, "uniqueId", "unique_id", "username", default="") if isinstance(payload, dict) else ""
    if not nickname:
        nickname = _ci_get(payload, "nickname", "nickName", "displayName", "display_name", default="") if isinstance(payload, dict) else ""

    avatar = ""
    # Use the largest source first. Older builds preferred avatarThumb, so the
    # preview window enlarged a 100-ish px thumbnail and naturally looked blurry.
    for key in (
        "avatarLarger", "avatar_larger",
        "avatarMedium", "avatar_medium",
        "profilePicture", "profile_picture",
        "avatarThumb", "avatar_thumb",
    ):
        avatar = _image_url(_ci_get(user, key))
        if avatar:
            break

    def truthy(v):
        if isinstance(v, bool):
            return v
        if isinstance(v, (int, float)):
            return v != 0
        return str(v or "").strip().casefold() in {"1", "true", "yes", "on"}

    role = ""
    identity = _find_first(payload, ("userIdentity", "user_identity"))
    identity = identity if isinstance(identity, dict) else {}
    if truthy(_ci_get(user, "isModerator", "is_moderator", "moderator", default=False)):
        role = "moderator"
    elif truthy(_ci_get(user, "isSubscriber", "is_subscriber", "isSubscribe", "is_subscribe", "subscriber", default=False)) \
            or truthy(_ci_get(identity, "isSubscriberOfAnchor", "is_subscriber_of_anchor", default=False)):
        role = "subscriber"
    else:
        badges = _ci_get(user, "badges", "badge", default=[])
        try:
            badge_text = json.dumps(badges, ensure_ascii=False).casefold()
        except Exception:
            badge_text = str(badges).casefold()
        if "moderator" in badge_text or "admin" in badge_text:
            role = "moderator"
        elif "subscriber" in badge_text or "subscription" in badge_text or "sub_" in badge_text:
            role = "subscriber"

    return str(username or "").strip(), str(nickname or "").strip(), avatar, role


def extract_viewer_count(event):
    """Extract *concurrent* viewers only from room-user-sequence style data."""
    value = _find_first(event, (
        "viewerCount", "viewer_count", "totalUser", "total_user",
        "currentViewers", "current_viewers", "userCount", "user_count",
    ))
    return max(0, _to_int(value))


def _method_and_payload(item):
    if not isinstance(item, dict):
        return "", {}

    current = item
    inherited_method = ""
    generic = {"", "message", "event", "data", "webcast", "websocketserverevent"}

    for _ in range(4):
        if not isinstance(current, dict):
            break
        raw_method = _ci_get(current, "method", "type", "event", "eventType", "event_type", "name", default="")
        current_method = str(raw_method or "")
        meaningful = current_method.casefold() not in generic
        if meaningful:
            inherited_method = current_method

        wrapper = None
        for key in ("data", "payload", "eventData", "event_data", "decodedData", "decoded_data"):
            candidate = _ci_get(current, key)
            if isinstance(candidate, dict):
                wrapper = candidate
                break
            if isinstance(candidate, str):
                parsed = _as_dict(candidate)
                if parsed:
                    wrapper = parsed
                    break

        if wrapper is None:
            return inherited_method, current

        nested_raw = _ci_get(wrapper, "method", "type", "event", "eventType", "event_type", "name", default="")
        nested_meaningful = str(nested_raw or "").casefold() not in generic

        # Once an actual event type is known, its data object is the payload.
        # Do not keep unwrapping fields inside a WebcastChatMessage/GiftMessage.
        if meaningful and not nested_meaningful:
            return inherited_method, wrapper

        current = wrapper

    return inherited_method, current if isinstance(current, dict) else {}


def normalize_euler_message(item):
    """Normalize one Euler decoded Webcast message into this app's event schema.

    Returns a dictionary or None. The parser intentionally accepts both v1/v2
    naming conventions because Euler's public WebSocket API may evolve its JSON
    casing without changing the underlying Webcast event names.
    """
    method, payload = _method_and_payload(item)
    m = method.casefold()
    if not m:
        # A nested wrapper may carry the actual event name.
        nested = _find_first(item, ("method", "eventType", "event_type"))
        if nested:
            method = str(nested)
            m = method.casefold()

    # Fallback for alias-style messages (chat/gift/like/member/roomUser) or
    # gateway wrappers where the type name was omitted but the decoded payload
    # is self-describing. Keep viewer detection conservative to avoid using
    # popularity/like totals as concurrent viewers.
    if not m:
        if _find_first(payload, ("comment",)) is not None:
            m = "chat"
        elif _find_first(payload, ("gift", "giftId", "gift_id")) is not None:
            m = "gift"
        elif _find_first(payload, ("likeCount", "like_count")) is not None:
            m = "like"

    username, nickname, avatar, role = _user_info(payload)
    user_fields = {
        "username": username,
        "nickname": nickname or username,
        "avatar_url": avatar,
        "role": role,
    }

    if "webcastchatmessage" in m or ("chat" in m and "emote" not in m):
        text = _find_first(payload, ("comment", "text", "content"))
        if text is None:
            text = ""
        return {"type": "chat", "message": str(text), "chat_source": "comment", **user_fields}

    if "emotechat" in m or ("emote" in m and "chat" in m):
        text = _find_first(payload, ("comment", "text", "content")) or "🎭"
        return {"type": "chat", "message": str(text), "chat_source": "emote", **user_fields}

    if "giftmessage" in m or m.endswith("gift") or m == "gift":
        gift = _find_first(payload, ("gift",))
        gift = gift if isinstance(gift, dict) else {}
        gift_name = _ci_get(gift, "name", "giftName", "gift_name", default="") or _find_first(payload, ("giftName", "gift_name")) or "Gift"
        gift_id = _ci_get(gift, "id", "giftId", "gift_id", default=0) or _find_first(payload, ("giftId", "gift_id")) or 0
        coins = _ci_get(gift, "diamondCount", "diamond_count", "coins", default=0) or _find_first(payload, ("diamondCount", "diamond_count")) or 0
        count = _find_first(payload, ("repeatCount", "repeat_count", "comboCount", "combo_count", "count")) or 1
        count = max(1, _to_int(count, 1))
        coins = max(0, _to_int(coins))
        gift_img = ""
        for key in ("image", "icon", "giftImage", "gift_image"):
            gift_img = _image_url(_ci_get(gift, key))
            if gift_img:
                break
        return {
            "type": "gift", "gift_name": str(gift_name), "gift_id": _to_int(gift_id),
            "gift_count": count, "gift_coins": coins, "diamond_count": coins * count,
            "gift_image_url": gift_img, **user_fields,
        }

    if "likemessage" in m or m.endswith("like") or m == "like":
        count = _find_first(payload, ("count", "likeCount", "like_count")) or 0
        total = _find_first(payload, ("totalLikes", "total_likes", "totalLikeCount", "total_like_count", "total")) or 0
        count = max(0, _to_int(count)); total = max(0, _to_int(total))
        if count <= 0 and total <= 0:
            return None
        return {"type": "like", "like_count": count, "total_like_count": total, **user_fields}

    if "roomuserseq" in m or "room_user_seq" in m or m == "roomuser":
        count = extract_viewer_count(payload)
        if count <= 0:
            return None
        return {"type": "viewer", "viewer_count": count, "viewer_source": "room_user_seq"}

    if "membermessage" in m or m.endswith("member") or m == "join":
        action = _to_int(_find_first(payload, ("action", "actionType", "action_type")), 1)
        if action not in (0, 1):
            return None
        return {"type": "join", **user_fields}

    if "socialmessage" in m or m == "follow":
        action = _to_int(_find_first(payload, ("action", "actionType", "action_type")), 0)
        display = str(_find_first(payload, ("displayType", "display_type", "label", "content")) or "").casefold()
        if action == 1 or "follow" in display or "takip" in display or m == "follow":
            return {"type": "follow", **user_fields}
        return None

    if "subnotifymessage" in m or "subscribe" in m or "subscription" in m:
        return {"type": "subscribe", "role": "subscriber", **{k: v for k, v in user_fields.items() if k != "role"}}

    if "controlmessage" in m:
        action = _to_int(_find_first(payload, ("action",)), 0)
        if action == 3:
            return {"type": "disconnected", "reason": "stream_end"}

    return None


def iter_euler_messages(document):
    """Yield individual Euler DecodedData objects from bundled JSON frames."""
    if isinstance(document, str):
        try:
            document = json.loads(document)
        except Exception:
            return
    if isinstance(document, list):
        for item in document:
            yield from iter_euler_messages(item)
        return
    if not isinstance(document, dict):
        return

    for bundle_key in ("messages", "events"):
        messages = _ci_get(document, bundle_key, default=None)
        if isinstance(messages, str):
            try:
                messages = json.loads(messages)
            except Exception:
                messages = None
        if isinstance(messages, list):
            for item in messages:
                if isinstance(item, dict):
                    yield item
            return

    # Some gateways put the bundle one level under data/response/result.
    for key in ("data", "response", "result"):
        child = _ci_get(document, key)
        if isinstance(child, (dict, list, str)):
            yielded = list(iter_euler_messages(child))
            if yielded:
                for item in yielded:
                    yield item
                return

    yield document


class TikTokLiveAdapter:
    """Native Euler Stream managed-WebSocket adapter.

    Earlier builds used Euler only as a signing server and then connected directly
    to TikTok's Webcast WebSocket. That path can be rejected with HTTP 400 even
    after a successful signature. This adapter uses Euler's managed production
    WebSocket endpoint directly, so TikTokLive's direct-WebSocket handshake is no
    longer part of the normal connection path.
    """

    def __init__(self, username, api_key, event_cb, status_cb):
        self.username = str(username or "").lstrip("@").strip()
        self.api_key = str(api_key or "").strip()
        self.event_cb = event_cb
        self.status_cb = status_cb
        self.thread = None
        self.loop = None
        self.ws = None
        self._stopping = False

    def start(self):
        if self.thread and self.thread.is_alive():
            return
        self._stopping = False
        self.thread = threading.Thread(target=self._thread, name="EulerStream", daemon=True)
        self.thread.start()

    def stop(self):
        self._stopping = True
        if self.ws is not None and self.loop and not self.loop.is_closed():
            try:
                future = asyncio.run_coroutine_threadsafe(self.ws.close(code=1000), self.loop)
                future.result(timeout=5)
            except Exception:
                pass

    def _thread(self):
        try:
            asyncio.run(self._run())
        except Exception as exc:
            if self._stopping:
                return
            detail = self._friendly_exception(exc)
            # Never surface the API key if an underlying network exception echoes the URL.
            if self.api_key:
                from urllib.parse import quote_plus
                detail = detail.replace(self.api_key, "***").replace(quote_plus(self.api_key), "***")
            self.status_cb("BAĞLANTI HATASI • " + detail)
            self.event_cb({"type": "connection_error", "error": detail})

    @staticmethod
    def _friendly_exception(exc):
        code = getattr(exc, "code", None)
        reason = getattr(exc, "reason", None)
        if code in CLOSE_MESSAGES:
            return CLOSE_MESSAGES[code]

        # websockets >= 14 exposes an HTTP response object on InvalidStatus.
        response = getattr(exc, "response", None)
        status_code = getattr(response, "status_code", None) or getattr(exc, "status_code", None)
        if status_code:
            if int(status_code) in (401, 403):
                return f"Euler WebSocket yetkilendirmesi reddedildi (HTTP {status_code}). API anahtarını ve hesabın WebSocket erişimini kontrol edin."
            if int(status_code) == 429:
                return "Euler bağlantı/rate limit sınırı aşıldı (HTTP 429)."
            return f"Euler WebSocket sunucusu HTTP {status_code} döndürdü."

        text = str(exc).strip()
        if reason:
            text = f"{text} • {reason}" if text else str(reason)
        return text or type(exc).__name__

    async def _run(self):
        if not self.username:
            raise RuntimeError("TikTok kullanıcı adı boş.")
        if not self.api_key:
            raise RuntimeError("Euler API anahtarı boş.")

        try:
            from websockets.asyncio.client import connect as ws_connect
        except ImportError:  # websockets 11-13 compatibility
            import websockets
            ws_connect = websockets.connect

        self.loop = asyncio.get_running_loop()
        url = build_euler_ws_url(self.username, self.api_key)
        self.status_cb("BAĞLANIYOR • Euler managed WebSocket açılıyor...")

        try:
            async with ws_connect(
                url,
                open_timeout=20,
                close_timeout=5,
                ping_interval=20,
                ping_timeout=20,
                max_size=None,
            ) as ws:
                self.ws = ws
                self.status_cb(f"BAĞLANDI • Euler WebSocket • @{self.username}")
                self.event_cb({"type": "connected", "room_id": "", "connection_source": "euler_ws"})

                async for raw in ws:
                    if self._stopping:
                        break
                    if isinstance(raw, bytes):
                        try:
                            raw = raw.decode("utf-8")
                        except UnicodeDecodeError:
                            continue
                    try:
                        document = json.loads(raw)
                    except (TypeError, json.JSONDecodeError):
                        continue

                    for item in iter_euler_messages(document):
                        event = normalize_euler_message(item)
                        if event:
                            self.event_cb(event)
                            if event.get("type") == "disconnected":
                                return
        finally:
            self.ws = None

        if not self._stopping:
            self.status_cb("BAĞLANTI KAPANDI • Euler WebSocket kapandı")
            self.event_cb({"type": "disconnected"})
