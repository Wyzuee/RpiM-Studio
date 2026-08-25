import sqlite3
import threading
import time
from datetime import datetime

class Database:
    def __init__(self, path):
        self.conn = sqlite3.connect(str(path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._pending = 0
        self.lock = threading.RLock()
        self.conn.executescript('''
        CREATE TABLE IF NOT EXISTS sessions(id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT, started_at TEXT, ended_at TEXT, room_id TEXT);
        CREATE TABLE IF NOT EXISTS events(
            id INTEGER PRIMARY KEY AUTOINCREMENT, session_id INTEGER, ts TEXT, type TEXT,
            username TEXT, nickname TEXT, message TEXT, gift_name TEXT,
            gift_count INTEGER DEFAULT 0, diamond_count INTEGER DEFAULT 0, gift_id INTEGER DEFAULT 0, gift_coins INTEGER DEFAULT 0, gift_image_url TEXT DEFAULT '', like_count INTEGER DEFAULT 0,
            viewer_count INTEGER DEFAULT 0, avatar_url TEXT DEFAULT '', role TEXT DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS idx_events_session ON events(session_id);
        CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts);
        CREATE INDEX IF NOT EXISTS idx_events_type ON events(session_id,type);
        ''')
        cols={r[1] for r in self.conn.execute('PRAGMA table_info(events)').fetchall()}
        if 'avatar_url' not in cols: self.conn.execute("ALTER TABLE events ADD COLUMN avatar_url TEXT DEFAULT ''")
        if 'role' not in cols: self.conn.execute("ALTER TABLE events ADD COLUMN role TEXT DEFAULT ''")
        if 'gift_id' not in cols: self.conn.execute("ALTER TABLE events ADD COLUMN gift_id INTEGER DEFAULT 0")
        if 'gift_coins' not in cols: self.conn.execute("ALTER TABLE events ADD COLUMN gift_coins INTEGER DEFAULT 0")
        if 'gift_image_url' not in cols: self.conn.execute("ALTER TABLE events ADD COLUMN gift_image_url TEXT DEFAULT ''")
        self.conn.commit()

    def start_session(self, username, room_id=''):
        cur=self.conn.execute('INSERT INTO sessions(username,started_at,room_id) VALUES(?,?,?)',(username,datetime.now().isoformat(timespec='seconds'),room_id))
        self.conn.commit(); return cur.lastrowid
    def end_session(self,sid):
        self.conn.execute('UPDATE sessions SET ended_at=? WHERE id=?',(datetime.now().isoformat(timespec='seconds'),sid)); self.conn.commit()
    def add_event(self,sid,typ,**e):
        with self.lock:
            return self._add_event_locked(sid,typ,**e)

    def _add_event_locked(self,sid,typ,**e):
        self.conn.execute('''INSERT INTO events(session_id,ts,type,username,nickname,message,gift_name,gift_count,diamond_count,gift_id,gift_coins,gift_image_url,like_count,viewer_count,avatar_url,role)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',(sid,e.get('ts',datetime.now().isoformat(timespec='seconds')),typ,e.get('username',''),e.get('nickname',''),e.get('message',''),e.get('gift_name',''),int(e.get('gift_count',0) or 0),int(e.get('diamond_count',0) or 0),int(e.get('gift_id',0) or 0),int(e.get('gift_coins',0) or 0),str(e.get('gift_image_url','') or ''),int(e.get('like_count',0) or 0),int(e.get('viewer_count',0) or 0),str(e.get('avatar_url','') or ''),str(e.get('role','') or '')))
        self._pending+=1
        if self._pending>=50:self.flush()
    def flush(self):
        with self.lock:
            if self._pending:self.conn.commit(); self._pending=0
    def summary(self,sid):
        self.flush()
        r=self.conn.execute('''SELECT COALESCE(SUM(CASE WHEN type='gift' THEN gift_count END),0) gifts,COALESCE(SUM(CASE WHEN type='gift' THEN diamond_count END),0) diamonds,
        COALESCE(SUM(CASE WHEN type='like' THEN like_count END),0) likes,COUNT(CASE WHEN type='follow' THEN 1 END) follows,COUNT(CASE WHEN type='chat' THEN 1 END) chats,
        COALESCE(MAX(viewer_count),0) max_viewers FROM events WHERE session_id=?''',(sid,)).fetchone()
        latest=self.conn.execute("SELECT viewer_count FROM events WHERE session_id=? AND type='viewer' ORDER BY id DESC LIMIT 1",(sid,)).fetchone()
        d=dict(r); d['viewers']=latest['viewer_count'] if latest else 0; return d
    def followers(self,sid,since=None):
        self.flush()
        q='SELECT ts,COALESCE(NULLIF(nickname,\'\'),username) user,avatar_url FROM events WHERE session_id=? AND type=\'follow\''; args=[sid]
        if since:q+=' AND ts>=?';args.append(since)
        return self.conn.execute(q+' ORDER BY id DESC',args).fetchall()
    def gifts(self,sid,limit=100):
        self.flush()
        return self.conn.execute('''SELECT COALESCE(NULLIF(MAX(e.nickname),''),MAX(e.username)) user,
        SUM(e.gift_count) gifts,SUM(e.diamond_count) diamonds,MAX(e.avatar_url) avatar_url,
        (SELECT e2.gift_name FROM events e2 WHERE e2.session_id=? AND e2.type='gift' AND e2.username=e.username ORDER BY e2.id DESC LIMIT 1) gift_name
        FROM events e WHERE e.session_id=? AND e.type='gift' GROUP BY e.username ORDER BY diamonds DESC,gifts DESC LIMIT ?''',(sid,sid,limit)).fetchall()

    def recent_gifts(self,sid,limit=100):
        self.flush()
        return self.conn.execute("SELECT ts,COALESCE(NULLIF(nickname,''),username) user,username,gift_name,gift_count,diamond_count,gift_coins,gift_image_url,avatar_url FROM events WHERE session_id=? AND type='gift' ORDER BY id DESC LIMIT ?",(sid,limit)).fetchall()
    def likes(self,sid,limit=100):
        self.flush()
        return self.conn.execute('''SELECT COALESCE(NULLIF(MAX(nickname),''),MAX(username)) user,SUM(like_count) likes,MAX(avatar_url) avatar_url
        FROM events WHERE session_id=? AND type='like' GROUP BY username ORDER BY likes DESC,user COLLATE NOCASE LIMIT ?''',(sid,limit)).fetchall()
    def joins(self,sid,limit=500):
        self.flush()
        return self.conn.execute("SELECT ts,COALESCE(NULLIF(nickname,''),username) user,username,nickname,avatar_url,role FROM events WHERE session_id=? AND type='join' ORDER BY id DESC LIMIT ?",(sid,limit)).fetchall()
    def chats(self,sid,limit=2000):
        self.flush()
        return self.conn.execute('''SELECT ts,COALESCE(NULLIF(nickname,''),username) user,message,avatar_url,username,nickname,role FROM events WHERE session_id=? AND type='chat' ORDER BY id DESC LIMIT ?''',(sid,limit)).fetchall()
    def recent_events(self,sid,limit=250):
        self.flush()
        return self.conn.execute('''SELECT ts,type,COALESCE(NULLIF(nickname,''),username) user,message,gift_name,like_count,viewer_count FROM events WHERE session_id=? ORDER BY id DESC LIMIT ?''',(sid,limit)).fetchall()
    def hourly_gifts(self,sid):
        return self.conn.execute("SELECT substr(ts,1,13) hour,SUM(gift_count) gifts,SUM(diamond_count) diamonds FROM events WHERE session_id=? AND type='gift' GROUP BY substr(ts,1,13) ORDER BY hour",(sid,)).fetchall()
    def session(self,sid):
        r=self.conn.execute('SELECT * FROM sessions WHERE id=?',(sid,)).fetchone(); return dict(r) if r else {}
    def close(self): self.flush(); self.conn.close()

# Serialize all SQLite access on the shared connection. Browser Source requests run
# in worker threads while the Qt GUI writes events, so a re-entrant lock prevents
# transient contention from dropping chat/gift/like events.
def _locked_method(method):
    def wrapper(self, *args, **kwargs):
        with self.lock:
            return method(self, *args, **kwargs)
    wrapper.__name__ = getattr(method, '__name__', 'locked')
    wrapper.__doc__ = getattr(method, '__doc__', None)
    return wrapper

for _method_name in (
    'start_session','end_session','add_event','flush','summary','followers',
    'gifts','recent_gifts','likes','joins','chats','recent_events','hourly_gifts',
    'session','close'
):
    if hasattr(Database, _method_name):
        setattr(Database, _method_name, _locked_method(getattr(Database, _method_name)))
