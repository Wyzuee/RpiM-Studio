import threading
from pathlib import Path
import time


def play_event_sound(kind, custom_path='', duration_seconds=0):
    """Play an event sound. duration_seconds=0 means play the full file."""
    def run():
        try:
            path = Path(custom_path) if custom_path else None
            if path and path.is_file():
                # pygame-ce supports MP3/WAV/OGG and allows deterministic stopping.
                try:
                    import pygame
                    pygame.mixer.init()
                    pygame.mixer.music.load(str(path))
                    pygame.mixer.music.play()
                    if duration_seconds and float(duration_seconds) > 0:
                        time.sleep(max(0.05, float(duration_seconds)))
                        pygame.mixer.music.stop()
                    else:
                        while pygame.mixer.music.get_busy():
                            time.sleep(0.03)
                    return
                except Exception:
                    pass
                # WAV fallback without an external multimedia stack.
                if path.suffix.lower() == '.wav':
                    import winsound
                    flags = winsound.SND_FILENAME | winsound.SND_ASYNC
                    winsound.PlaySound(str(path), flags)
                    if duration_seconds and float(duration_seconds) > 0:
                        time.sleep(max(0.05, float(duration_seconds)))
                        winsound.PlaySound(None, winsound.SND_PURGE)
                    return
            import winsound
            tones={'follow':(900,120),'gift':(1200,160),'like':(700,80),'chat':(500,60)}
            f,d=tones.get(kind,(800,100)); winsound.Beep(f,d)
        except Exception:
            pass
    threading.Thread(target=run,daemon=True).start()
