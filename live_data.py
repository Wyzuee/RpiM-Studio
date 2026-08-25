from datetime import datetime


def record_dict(row):
    """Return a plain dict for sqlite3.Row, dict, or mapping-like records."""
    if row is None:
        return {}
    if isinstance(row, dict):
        return dict(row)
    try:
        return dict(row)
    except Exception:
        pass
    out = {}
    keys = getattr(row, 'keys', None)
    if callable(keys):
        try:
            for key in keys():
                out[key] = row[key]
        except Exception:
            pass
    return out


def display_user(record):
    r = record_dict(record)
    return str(r.get('user') or r.get('nickname') or r.get('username') or '').strip()


def normalize_live_record(record, *, default_ts=True):
    r = record_dict(record)
    if default_ts and not r.get('ts'):
        r['ts'] = datetime.now().isoformat(timespec='seconds')
    if not r.get('user'):
        r['user'] = display_user(r)
    r.setdefault('username', '')
    r.setdefault('nickname', '')
    r.setdefault('message', '')
    r.setdefault('role', '')
    r.setdefault('avatar_url', '')
    return r


def merge_chat_records(db_rows_newest_first, cache_rows, limit=2000):
    """Merge persisted SQLite chat rows with in-memory rows safely.

    SQLite rows intentionally do not implement dict.get().  Older builds treated
    them as dictionaries, which crashed the GUI/browser snapshot as soon as the
    first chat arrived.  This helper normalizes both sources before de-duplication.
    """
    db_rows = [normalize_live_record(r) for r in reversed(list(db_rows_newest_first or []))]
    cache = [normalize_live_record(r) for r in list(cache_rows or [])]

    def key(r):
        return (
            str(r.get('username') or '').casefold(),
            str(r.get('message') or ''),
            str(r.get('ts') or ''),
        )

    merged = []
    seen = set()
    for row in db_rows + cache:
        k = key(row)
        if k in seen:
            continue
        seen.add(k)
        merged.append(row)
    if limit:
        merged = merged[-int(limit):]
    return merged
