import asyncio
import os
import queue
import re
import tempfile
import threading
import time
import unicodedata


_EMOJI_RANGES = (
    (0x1F000, 0x1FAFF),  # emoji / pictographs / flags / symbols
    (0x2600, 0x27BF),    # misc symbols + dingbats
    (0x2300, 0x23FF),
    (0x2B00, 0x2BFF),
)


def _is_emoji_char(ch):
    cp = ord(ch)
    if cp in (0x200D, 0xFE0F):  # ZWJ / variation selector
        return True
    if any(lo <= cp <= hi for lo, hi in _EMOJI_RANGES):
        return True
    # Most emoji-like pictographs are Symbol/Other. Keep plain ©/® etc. harmless.
    return unicodedata.category(ch) == 'So' and cp > 0x2500


def strip_emojis(text):
    """Remove emoji glyphs without removing normal Turkish text/punctuation."""
    out = []
    skip_joined = False
    for ch in str(text or ''):
        if _is_emoji_char(ch):
            skip_joined = True
            continue
        # Emoji skin-tone modifiers.
        if 0x1F3FB <= ord(ch) <= 0x1F3FF:
            continue
        out.append(ch)
        skip_joined = False
    return re.sub(r'\s{2,}', ' ', ''.join(out)).strip()


def _norm_token(s):
    return re.sub(r'[^0-9a-zçğıöşü]+', '', str(s or '').casefold())


def looks_like_spam(text):
    """Conservative spam detector: repeated chars/tokens/patterns and symbol floods."""
    raw = str(text or '').strip()
    if not raw:
        return False
    low = raw.casefold()
    compact = re.sub(r'\s+', '', low)
    # aaaaaaa / !!!!!!!!
    if re.search(r'(.)\1{5,}', compact, flags=re.S):
        return True
    # asdasdasd / hahaha... / 123123123. Require >= 3 repeats.
    if re.fullmatch(r'(.{1,4})\1{2,}', compact, flags=re.S) and len(compact) >= 6:
        return True
    words = re.findall(r'[\wçğıöşü]+', low, flags=re.UNICODE)
    if len(words) >= 4 and len(set(words)) == 1:
        return True
    # Heavy punctuation/symbol flood. Emoji-only is handled separately too.
    if len(raw) >= 8:
        noisy = sum(1 for ch in raw if not (ch.isalnum() or ch.isspace()))
        if noisy / max(1, len(raw)) >= 0.72:
            return True
    return False


def looks_like_random(text):
    """Detect common keyboard-mash/random strings without rejecting normal sentences."""
    raw = str(text or '').casefold().strip()
    if not raw:
        return False
    compact = _norm_token(raw)
    if len(compact) < 6:
        return False
    # Common TR/internet keyboard mashes: asdasd, sjsjsj, kdkdkd, qweqwe, zxc...
    if re.fullmatch(r'(?:(?:asd|qwe|zxc|sdf|dfg|fgh|ghj|hjk|jkl|sjs|jsj|kdk|dks|ksk|xd|lol)){2,}', compact):
        return True
    if re.fullmatch(r'(.{2,3})\1{2,}', compact) and len(compact) >= 6:
        return True
    # Long consonant-only tokens are usually keyboard mash. Turkish vowels included.
    letters = ''.join(ch for ch in compact if ch.isalpha())
    vowels = set('aeıioöuü')
    if len(letters) >= 8 and not any(ch in vowels for ch in letters):
        return True
    return False


def contains_filtered_word(text, words_text):
    msg = str(text or '').casefold()
    entries = [x.strip().casefold() for x in re.split(r'[,;\n]+', str(words_text or '')) if x.strip()]
    for term in entries:
        if ' ' in term:
            if term in msg:
                return True
        else:
            if re.search(r'(?<!\w)' + re.escape(term) + r'(?!\w)', msg, flags=re.UNICODE):
                return True
    return False


class ChatReader:
    """Single-worker TTS queue with independent content filters.

    Unlike older builds, a new chat message no longer clears every queued message.
    This prevents rapid chat from silently dropping comments before TTS can read them.
    """
    def __init__(self, settings):
        self.settings = settings
        self._q = queue.Queue(maxsize=120)
        self._stop = threading.Event()
        self._recent = {}  # (username, normalized message) -> monotonic time
        self._worker = threading.Thread(target=self._worker_loop, daemon=True, name='ChatTTS')
        self._worker.start()

    def update_settings(self, settings):
        self.settings = settings

    def prepare_text(self, text, username='', nickname=''):
        """Return text to speak, or '' when one of the selected filters rejects it."""
        s = self.settings
        raw = str(text or '').strip()
        if not raw:
            return ''

        # Explicit emote-only event filtering remains backward compatible.
        if bool(s.get('ai_skip_filtered_words', True)) and contains_filtered_word(raw, s.get('ai_filtered_words', '')):
            return ''
        if bool(s.get('ai_skip_spam', True)) and looks_like_spam(raw):
            return ''
        if bool(s.get('ai_skip_random', True)) and looks_like_random(raw):
            return ''

        spoken = raw
        if bool(s.get('ai_skip_emojis', True)):
            spoken = strip_emojis(spoken)
            if not spoken:
                return ''

        # Treat repeated same-user/same-message comments as spam for a short window.
        if bool(s.get('ai_skip_spam', True)):
            key = (str(username or nickname or '').casefold().strip(), re.sub(r'\s+', ' ', spoken.casefold()))
            now = time.monotonic()
            last = self._recent.get(key, 0.0)
            self._recent[key] = now
            # Small cleanup prevents an unbounded dict on long streams.
            if len(self._recent) > 2000:
                cutoff = now - 60.0
                self._recent = {k: v for k, v in self._recent.items() if v >= cutoff}
            if last and (now - last) < 20.0:
                return ''

        if bool(s.get('read_names', True)):
            speaker = str(nickname or username or '').strip()
            if speaker:
                spoken = f'{speaker}: {spoken}'
        return spoken.strip()

    def speak(self, text, username='', nickname=''):
        s = self.settings
        if not s.get('ai_enabled') or not s.get('ai_auto_read'):
            return False
        spoken = self.prepare_text(text, username=username, nickname=nickname)
        if not spoken:
            return False
        try:
            self._q.put_nowait(spoken)
        except queue.Full:
            # Drop only the oldest queued line, never flush the whole queue.
            try:
                self._q.get_nowait(); self._q.task_done()
            except queue.Empty:
                pass
            try:
                self._q.put_nowait(spoken)
            except queue.Full:
                return False
        return True

    def stop(self):
        self._stop.set()
        try: self._q.put_nowait(None)
        except queue.Full: pass

    def _worker_loop(self):
        while not self._stop.is_set():
            text = self._q.get()
            if text is None:
                self._q.task_done(); break
            try:
                snapshot = dict(getattr(self.settings, 'data', self.settings))
                self._run(text, snapshot)
            except Exception:
                pass
            finally:
                self._q.task_done()

    def _run(self, text, settings):
        voice_id = str(settings.get('ai_voice_id', '') or '')
        if voice_id.startswith('edge:'):
            try:
                import edge_tts
                from playsound3 import playsound
                async def make(path):
                    await edge_tts.Communicate(text, voice=voice_id[5:]).save(path)
                fd, path = tempfile.mkstemp(suffix='.mp3'); os.close(fd)
                try:
                    asyncio.run(make(path))
                    playsound(path, block=True)
                finally:
                    try: os.remove(path)
                    except OSError: pass
                return
            except Exception:
                pass
        try:
            import pyttsx3
            engine = pyttsx3.init()
            engine.setProperty('rate', int(settings.get('ai_voice_rate', 170)))
            if voice_id:
                try: engine.setProperty('voice', voice_id)
                except Exception: pass
            else:
                lang = str(settings.get('ai_language', 'tr-TR')).lower()
                for v in engine.getProperty('voices') or []:
                    vid = str(getattr(v, 'id', '') or '')
                    meta = (str(getattr(v, 'languages', '') or '') + ' ' + str(getattr(v, 'name', '') or '')).lower()
                    if lang in meta or lang[:2] in meta:
                        engine.setProperty('voice', vid); break
            engine.say(text); engine.runAndWait(); engine.stop()
        except Exception:
            pass
