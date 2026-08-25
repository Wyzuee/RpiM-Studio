import json, os, shutil
from pathlib import Path
from app_paths import app_data_root

DEFAULTS={
    'euler_api_key':'',
    'sound_enabled':True,
    'sound_follow':True,
    'sound_gift':True,
    'sound_like':False,
    'sound_chat':False,
    'sound_file_follow':'',
    'sound_file_gift':'',
    'sound_file_like':'',
    'sound_file_chat':'',
    'sound_duration_follow':0,
    'sound_duration_gift':0,
    'sound_duration_like':0,
    'sound_duration_chat':0,
    'browser_port':8765,
    'ai_enabled':False,
    'ai_auto_read':False,
    'ai_voice_rate':170,
    'ai_ignore_emotes':False,
    'ai_skip_emojis':True,
    'ai_skip_spam':True,
    'ai_skip_random':True,
    'ai_skip_filtered_words':True,
    'ai_filtered_words':'',
    'overlay_alpha':0,
    'ai_language':'tr-TR',
    'ai_voice_id':'',
    'read_all':True,
    'read_names':True,
    'read_followers':True,
    'read_gifters':True,
    'read_publisher':True,
    'read_moderators':True,
    'read_subscribers':True,
    'read_normal':True,
    'like_align':'left',
    'like_text_color':'#ff5b7f',
    'like_count_color':'#ffffff',
    'like_heart_color':'#ff2f67',
    'like_rgb_text':False,
    'like_wave_text':False,
    'like_glow_text':True,
    'like_avatar_size':34,
    'like_row_gap':6,
    'like_show_avatar':True,
    'like_show_title':True,
    'like_bg_alpha':48,
    'gift_align':'left',
    'gift_text_color':'#ffd166',
    'gift_rgb_text':False,
    'gift_wave_text':False,
    'gift_glow_text':True,
    'gift_avatar_size':34,
    'gift_row_gap':6,
    'gift_show_avatar':True,
    'gift_show_title':True,
    'gift_bg_alpha':48,
    'follow_align':'left',
    'follow_text_color':'#ffffff',
    'follow_rgb_text':False,
    'follow_wave_text':False,
    'follow_glow_text':False,
    'follow_avatar_size':34,
    'follow_row_gap':6,
    'follow_show_avatar':True,
    'follow_show_title':True,
    'follow_bg_alpha':48,
    'chat_align':'left',
    'chat_text_color':'#ffffff',
    'chat_rgb_text':False,
    'chat_wave_text':False,
    'chat_glow_text':False,
    'chat_avatar_size':34,
    'chat_row_gap':8,
    'chat_show_avatar':True,
    'chat_show_title':True,
    'chat_bg_alpha':48,
    'chat_font_size':18,
    'chat_title_size':20,
    'chat_widget_preset':'phone_480x800',
    'chat_widget_width':480,
    'chat_widget_height':800,
}

class Settings:
    CLOUD_EXCLUDE={
        'euler_api_key',
        'sound_file_follow','sound_file_gift','sound_file_like','sound_file_chat',
        'browser_port',
    }

    def __init__(self,base,account_id=None,cloud_store=None):
        # Store user settings outside the application folder so updates, ZIP re-extracts
        # and EXE builds do not wipe the user's choices. On Windows this resolves to
        # %APPDATA%\RpiM Studio\settings.json. Existing project-local settings are
        # migrated automatically on first run.
        root = app_data_root()
        self.account_id = str(account_id) if account_id is not None else None
        self.cloud_store = cloud_store
        global_path = root / 'settings.json'
        if self.account_id is not None:
            account_root = root / 'accounts' / str(self.account_id)
            account_root.mkdir(parents=True, exist_ok=True)
            self.path = account_root / 'settings.json'
        else:
            self.path = global_path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.legacy_path = Path(base) / 'data' / 'settings.json'
        # First account inherits the pre-account/global settings once so existing
        # Euler key, sound paths and widget styles are not lost after upgrading.
        if not self.path.exists():
            candidates=[]
            if self.account_id is not None:
                candidates.append(global_path)
                # V40-V42 used local numeric account folders. Carry the most recently
                # modified settings forward into the first global UUID account so an
                # existing Euler key/widget configuration is not lost on upgrade.
                try:
                    old_settings=[x for x in (root/'accounts').glob('*/settings.json') if x.parent.name != str(self.account_id)]
                    old_settings.sort(key=lambda x:x.stat().st_mtime, reverse=True)
                    candidates.extend(old_settings[:1])
                except Exception:
                    pass
            candidates.append(self.legacy_path)
            for candidate in candidates:
                if candidate != self.path and candidate.exists():
                    try:
                        shutil.copy2(candidate, self.path)
                        break
                    except Exception:
                        pass
        self.data=dict(DEFAULTS); self.load()
    def load(self):
        local_loaded={}
        try:
            local_loaded=json.loads(self.path.read_text(encoding='utf-8'))
            if isinstance(local_loaded,dict):
                self.data.update(local_loaded)
            for key in ('sound_duration_follow','sound_duration_gift','sound_duration_like','sound_duration_chat'):
                if key in local_loaded:
                    try:
                        value=float(local_loaded[key])
                        if value > 60: value=value/1000.0
                        self.data[key]=round(max(0.0,value),1)
                    except (TypeError,ValueError):
                        self.data[key]=0.0
        except Exception:
            local_loaded={}

        # Cloud settings override portable UI/widget preferences, while machine-local
        # values such as Euler key, local sound file paths and browser port stay local.
        cloud={}
        if self.cloud_store is not None:
            try:
                cloud=self.cloud_store.get_cloud_settings() or {}
            except Exception:
                cloud={}
        if isinstance(cloud,dict) and cloud:
            for key,value in cloud.items():
                if key not in self.CLOUD_EXCLUDE:
                    self.data[key]=value
            self._save_local()
        elif local_loaded and self.cloud_store is not None:
            try:
                self.cloud_store.save_cloud_settings(self.cloud_payload())
            except Exception:
                pass
        elif not self.path.exists():
            self._save_local()

    def cloud_payload(self):
        return {k:v for k,v in self.data.items() if k not in self.CLOUD_EXCLUDE}

    def _save_local(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix('.tmp')
        tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding='utf-8')
        tmp.replace(self.path)

    def save(self):
        self._save_local()
        if self.cloud_store is not None:
            try:
                self.cloud_store.save_cloud_settings(self.cloud_payload())
            except Exception:
                # Offline mode: local save must still succeed. Cloud sync will retry
                # on a later save/login.
                pass
    def get(self,k,default=None): return self.data.get(k,default)
    def set(self,k,v): self.data[k]=v
