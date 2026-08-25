from pathlib import Path
import importlib
import sqlite3
import sys
import time
import urllib.request

REQUIRED = ["PySide6", "websockets", "reportlab", "requests", "pyttsx3", "playsound3", "edge_tts"]

print("Python:", sys.version.split()[0])
if sys.version_info[:2] < (3, 11) or sys.version_info[:2] > (3, 13):
    print(f"[FAIL] Desteklenen Python: 3.11-3.13; bulunan: {sys.version_info.major}.{sys.version_info.minor}")
    sys.exit(1)
print("[OK] Python 3.11-3.13")

failed = []
for name in REQUIRED:
    try:
        mod = importlib.import_module(name)
        print(f"[OK] {name} {getattr(mod, '__version__', '')}")
    except Exception as exc:
        print(f"[FAIL] {name}: {type(exc).__name__}: {exc}")
        failed.append(name)

try:
    p = Path("data") / "diagnostic.sqlite3"
    p.parent.mkdir(exist_ok=True)
    con = sqlite3.connect(p)
    con.execute("CREATE TABLE IF NOT EXISTS t(x INTEGER)")
    con.execute("INSERT INTO t VALUES(1)")
    con.commit()
    assert con.execute("SELECT COUNT(*) FROM t").fetchone()[0] >= 1
    con.close()
    try:
        p.unlink()
    except OSError:
        pass
    print("[OK] SQLite smoke test")
except Exception as exc:
    print(f"[FAIL] SQLite: {type(exc).__name__}: {exc}")
    failed.append("sqlite")

# Native Euler JSON event-normalization smoke test. No network/API key required.
try:
    from tiktok.live_client import normalize_euler_message, extract_viewer_count
    chat = normalize_euler_message({
        "method": "WebcastChatMessage",
        "data": {"user": {"uniqueId": "tester", "nickname": "Tester"}, "content": "Merhaba"},
    })
    viewers = normalize_euler_message({"method": "WebcastRoomUserSeqMessage", "data": {"viewerCount": 27}})
    assert chat and chat["type"] == "chat" and chat["message"] == "Merhaba"
    assert viewers and viewers["viewer_count"] == 27
    assert extract_viewer_count({"total": 999, "popularity": 888}) == 0
    print("[OK] Euler event parser smoke test")
except Exception as exc:
    print(f"[FAIL] Euler parser: {type(exc).__name__}: {exc}")
    failed.append("euler_parser")


# Regression: sqlite3.Row + in-memory chat dicts must merge without .get crashes.
try:
    from database.database import Database
    from live_data import merge_chat_records, display_user
    p = Path("data") / "diagnostic_live.sqlite3"
    try: p.unlink()
    except OSError: pass
    db = Database(p)
    sid = db.start_session("tester")
    ts = "2026-08-25T00:00:00"
    db.add_event(sid, "chat", ts=ts, username="alice", nickname="Alice", message="Merhaba", role="")
    db.flush()
    cache = [{"type":"chat","ts":ts,"username":"alice","nickname":"Alice","message":"Merhaba","role":""},
             {"type":"chat","ts":"2026-08-25T00:00:01","username":"bob","nickname":"Bob","message":"Selam","role":"moderator"}]
    merged = merge_chat_records(db.chats(sid, 20), cache, 20)
    assert len(merged) == 2, merged
    assert display_user(merged[0]) == "Alice" and display_user(merged[1]) == "Bob"
    db.close()
    try: p.unlink()
    except OSError: pass
    print("[OK] Chat Row/cache merge regression test")
except Exception as exc:
    print(f"[FAIL] Chat merge regression: {type(exc).__name__}: {exc}")
    failed.append("chat_merge")

# Parser coverage using Euler's documented DecodedData {type,data} bundle shape.
try:
    from tiktok.live_client import iter_euler_messages, normalize_euler_message
    bundle = {"timestamp": 1, "messages": [
        {"type":"WebcastChatMessage","data":{"user":{"displayId":"alice","nickname":"Alice"},"comment":"hello"}},
        {"type":"WebcastGiftMessage","data":{"user":{"displayId":"bob","nickname":"Bob"},"gift":{"id":1,"name":"Rose","diamondCount":1},"repeatCount":2}},
        {"type":"WebcastLikeMessage","data":{"user":{"displayId":"carol","nickname":"Carol"},"count":5,"total":100}},
        {"type":"WebcastMemberMessage","data":{"user":{"displayId":"dave","nickname":"Dave"},"action":1}},
        {"type":"WebcastSocialMessage","data":{"user":{"displayId":"erin","nickname":"Erin"},"action":1,"displayType":"follow"}},
        {"type":"WebcastRoomUserSeqMessage","data":{"viewerCount":126}}
    ]}
    parsed=[normalize_euler_message(x) for x in iter_euler_messages(bundle)]
    nested = normalize_euler_message({"type":"event","data":{"type":"WebcastChatMessage","data":{"user":{"displayId":"nested"},"comment":"nested hello"}}})
    kinds=[x.get("type") for x in parsed if x]
    assert kinds == ["chat","gift","like","join","follow","viewer"], kinds
    assert parsed[0]["username"] == "alice" and parsed[0]["message"] == "hello"
    assert nested and nested["type"] == "chat" and nested["message"] == "nested hello"
    print("[OK] Euler bundled event coverage")
except Exception as exc:
    print(f"[FAIL] Euler bundled coverage: {type(exc).__name__}: {exc}")
    failed.append("euler_bundle")

# End-to-end list/widget snapshot regression using real SQLite rows.
try:
    from database.database import Database
    from browser_data import build_browser_snapshot
    p = Path("data") / "diagnostic_snapshot.sqlite3"
    try: p.unlink()
    except OSError: pass
    db = Database(p)
    sid = db.start_session("creator")
    base = "2026-08-25T00:01:00"
    db.add_event(sid,"chat",ts=base,username="alice",nickname="Alice",message="Merhaba",role="")
    db.add_event(sid,"gift",ts=base,username="bob",nickname="Bob",gift_name="Rose",gift_count=2,diamond_count=2,gift_coins=1)
    db.add_event(sid,"like",ts=base,username="carol",nickname="Carol",like_count=7)
    db.add_event(sid,"follow",ts=base,username="erin",nickname="Erin")
    db.add_event(sid,"join",ts=base,username="dave",nickname="Dave")
    db.add_event(sid,"viewer",ts=base,viewer_count=126)
    db.flush()
    payload = build_browser_snapshot(db,sid,{"viewers":126,"max":180},[],lambda r:'normal',lambda name:{"coins":1,"image_url":""})
    assert payload["viewers"] == 126 and payload["max"] == 180
    assert payload["chat"][0]["user"] == "Alice"
    assert payload["gifts"][0]["user"] == "Bob"
    assert payload["likes"][0]["user"] == "Carol"
    assert payload["followers"][0]["user"] == "Erin"
    assert payload["joins"][0]["user"] == "Dave"
    db.close()
    try: p.unlink()
    except OSError: pass
    print("[OK] Full list/widget SQLite snapshot regression")
except Exception as exc:
    print(f"[FAIL] Full snapshot regression: {type(exc).__name__}: {exc}")
    failed.append("full_snapshot")

# Local OBS Browser Source server smoke test.
try:
    from web_overlay import BrowserOverlayServer
    snapshot = lambda: {
        "chat": [{"user": "Tester", "message": "Merhaba", "cls": "normal"}],
        "gifts": [{"rank":"🥇","user":"Bob","value":"2 hediye","cls":"normal","avatar":"https://example.invalid/b.jpg"}], "recent-gifts": [], "likes": [{"rank":"🥇","user":"Carol","value":"5 ❤️","likes":5,"cls":"normal","avatar":"https://example.invalid/c.jpg"}], "followers": [{"rank":"","user":"Erin","value":"00:00:00","cls":"normal"}], "joins": [],
        "viewers": 12, "max": 20,
        "widget_style":{"align":"right","text_color":"#ff5b7f","heart_color":"#ff2f67","rgb_text":True,"wave_text":True,"glow_text":True,"avatar_size":36,"row_gap":5,"show_avatar":True,"show_title":True,"bg_alpha":48},
    }
    server = BrowserOverlayServer(snapshot, port=0)
    port = server.start()
    time.sleep(0.05)
    health = urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=2).read().decode("utf-8")
    page = urllib.request.urlopen(f"http://127.0.0.1:{port}/likes", timeout=2).read().decode("utf-8")
    api = urllib.request.urlopen(f"http://127.0.0.1:{port}/api/all", timeout=2).read().decode("utf-8")
    assert '"ok": true' in health
    assert "border-radius:50%" in page and "@keyframes heartPulse" in page and "@keyframes waveChar" in page and "@keyframes rgbShift" in page
    assert "Tester" in api and "Bob" in api and "Carol" in api and "Erin" in api and "widget_style" in api
    server.stop()
    print("[OK] OBS Browser Source smoke test")
except Exception as exc:
    try:
        server.stop()
    except Exception:
        pass
    print(f"[FAIL] OBS server: {type(exc).__name__}: {exc}")
    failed.append("obs_server")

if failed:
    print("FAILED:", ", ".join(failed))
    sys.exit(1)

# V30 TTS content-filter regression tests (no audio playback required).
try:
    from ai_reader import ChatReader
    cfg = {
        'ai_enabled': True, 'ai_auto_read': True, 'read_names': False,
        'ai_skip_emojis': True, 'ai_skip_spam': True, 'ai_skip_random': True,
        'ai_skip_filtered_words': True, 'ai_filtered_words': 'discord.gg, yasak kelime'
    }
    reader = ChatReader(cfg)
    assert reader.prepare_text('Merhaba 😂❤️', username='a') == 'Merhaba'
    assert reader.prepare_text('😂❤️🔥', username='b') == ''
    assert reader.prepare_text('aaaaaaaaaa', username='c') == ''
    assert reader.prepare_text('asdasdasd', username='d') == ''
    assert reader.prepare_text('discord.gg/test', username='e') == ''
    assert reader.prepare_text('Bugün yayın çok güzel', username='f') == 'Bugün yayın çok güzel'
    reader.stop()
    print('[OK] V30 TTS emoji/spam/random/filtered-word filters')
except Exception as exc:
    print(f'[FAIL] V30 TTS filters: {type(exc).__name__}: {exc}')
    failed.append('tts_filters')

# V30 separate like-count colour regression.
try:
    from web_overlay import page as widget_page
    html = widget_page('TOP BEĞENİ', 'likes')
    assert 'color:var(--like-count)!important' in html
    assert "safeColor(st.count_color,'#ffffff')" in html
    overlay_source = (Path('ui') / 'overlay.py').read_text(encoding='utf-8')
    assert 'class LikeCountLabel' in overlay_source
    assert "style.get('count_color','#ffffff')" in overlay_source
    print('[OK] V30 separate like-count colour pipeline')
except Exception as exc:
    print(f'[FAIL] V30 like-count colour: {type(exc).__name__}: {exc}')
    failed.append('like_count_color')


# V43 global Supabase account/config regression test (offline; no real signup).
try:
    import tempfile, shutil
    from auth import AccountStore, AuthError
    from cloud_config import SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY
    root = Path(tempfile.mkdtemp(prefix='rpim_cloud_auth_diag_'))
    store = AccountStore(root)
    assert SUPABASE_URL.startswith('https://') and SUPABASE_URL.endswith('.supabase.co')
    assert SUPABASE_PUBLISHABLE_KEY.startswith('sb_publishable_')
    assert store.validate_email('diagnostic@example.com') == 'diagnostic@example.com'
    assert store.validate_publisher('@diagnostic.live') == 'diagnostic.live'
    assert store.validate_password('StrongPass1!') == 'StrongPass1!'
    try:
        store.validate_password('weak')
        raise AssertionError('weak password accepted')
    except AuthError:
        pass
    protected=store._protect('refresh-token-test')
    assert store._unprotect(protected) == 'refresh-token-test'
    assert store._headers()['apikey'] == SUPABASE_PUBLISHABLE_KEY
    store.close()
    shutil.rmtree(root,ignore_errors=True)
    print('[OK] V43 global Supabase auth/config offline regression')
except Exception as exc:
    print(f'[FAIL] V43 global auth/config: {type(exc).__name__}: {exc}')
    failed.append('auth_system')

# V43 cloud settings split: portable settings sync, Euler/local file secrets do not.
try:
    import tempfile, shutil, os
    from settings import Settings
    class FakeCloud:
        def __init__(self):
            self.saved=None
        def get_cloud_settings(self):
            return {'chat_font_size':22,'like_count_color':'#abcdef','euler_api_key':'SHOULD_NOT_LOAD'}
        def save_cloud_settings(self,data):
            self.saved=dict(data)
    cloud=FakeCloud()
    old_appdata=os.environ.get('APPDATA')
    tmp=Path(tempfile.mkdtemp(prefix='rpim_settings_diag_'))
    os.environ['APPDATA']=str(tmp)
    cfg=Settings(Path('.'),'uuid-test',cloud_store=cloud)
    assert cfg.get('chat_font_size') == 22
    assert cfg.get('like_count_color') == '#abcdef'
    assert cfg.get('euler_api_key','') != 'SHOULD_NOT_LOAD'
    cfg.set('euler_api_key','LOCAL_EULER_KEY')
    cfg.save()
    assert cloud.saved is not None and 'euler_api_key' not in cloud.saved
    assert 'sound_file_follow' not in cloud.saved and 'browser_port' not in cloud.saved
    if old_appdata is None: os.environ.pop('APPDATA',None)
    else: os.environ['APPDATA']=old_appdata
    shutil.rmtree(tmp,ignore_errors=True)
    print('[OK] V43 cloud settings / local Euler-key separation')
except Exception as exc:
    print(f'[FAIL] V43 cloud settings split: {type(exc).__name__}: {exc}')
    failed.append('cloud_settings')

if failed:
    print('FAILED:', ', '.join(failed))
    sys.exit(1)

print('ALL DIAGNOSTICS PASSED')
