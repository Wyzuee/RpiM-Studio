from live_data import record_dict, merge_chat_records, display_user


def _css_class(classify, row):
    try:
        value = classify(row)
    except Exception:
        value = 'normal'
    return {
        'publisher': 'publisher',
        'moderator': 'moderator',
        'subscriber': 'subscriber',
        'love': 'love',
    }.get(value, 'normal')




def _role_icon(css_class):
    return {
        'publisher': '🎤',
        'moderator': '🛡️',
        'subscriber': '⭐',
        'love': '🧡',
        'normal': '💬',
    }.get(css_class or 'normal', '💬')

def build_browser_snapshot(db, sid, stats, chat_cache, classify, gift_resolve):
    """Build the JSON payload shared by every OBS Browser Source.

    This function is deliberately Qt-free so it can be regression-tested on
    Windows/Linux and catches data-shape bugs before the GUI is started.
    """
    if not sid:
        return {
            'viewers': 0, 'max': 0, 'chat': [], 'gifts': [],
            'recent-gifts': [], 'likes': [], 'followers': [], 'joins': [],
        }

    gift_badges = {}
    gifts = []
    for i, row in enumerate(db.gifts(sid, 50), 1):
        r = record_dict(row)
        rank = '🥇' if i == 1 else ('🥈' if i == 2 else ('🥉' if i == 3 else f'{i}#'))
        user_key = str(r.get('user') or r.get('username') or '').strip().lower()
        if i <= 3 and user_key:
            gift_badges[user_key] = ('🥇 Top 1' if i == 1 else ('🥈 Top 2' if i == 2 else '🥉 Top 3'))
        gifts.append({
            'rank': rank,
            'user': display_user(r) or '@?',
            'value': f"{r.get('gifts', 0)} hediye • {r.get('diamonds', 0)} puan",
            'cls': 'normal',
            'avatar': str(r.get('avatar_url','') or ''),
        })

    chats = merge_chat_records(db.chats(sid, 150), chat_cache, 150)
    chat = []
    for r in chats:
        user_key = str(r.get('username') or r.get('user') or '').strip().lower()
        css_cls = _css_class(classify, r)
        chat.append({
            'user': display_user(r) or '@?',
            'message': str(r.get('message', '')),
            'cls': css_cls,
            'icon': _role_icon(css_cls),
            'avatar': str(r.get('avatar_url','') or ''),
            'ts': str(r.get('ts','') or ''),
            'badge': gift_badges.get(user_key, ''),
        })

    likes = []
    for i, row in enumerate(db.likes(sid, 50), 1):
        r = record_dict(row)
        likes.append({
            'rank': '🥇' if i == 1 else ('🥈' if i == 2 else ('🥉' if i == 3 else f'{i}#')),
            'user': display_user(r) or '@?',
            'value': f"{r.get('likes', 0)} ❤️",
            'likes': int(r.get('likes',0) or 0),
            'cls': 'normal',
            'avatar': str(r.get('avatar_url','') or ''),
        })

    followers = []
    for row in db.followers(sid)[:50]:
        r = record_dict(row)
        followers.append({
            'rank': '', 'user': display_user(r) or '@?',
            'value': str(r.get('ts', ''))[11:19], 'cls': 'normal',
            'avatar': str(r.get('avatar_url','') or ''),
        })

    recent = []
    for row in reversed(db.recent_gifts(sid, 50)):
        r = record_dict(row)
        try:
            meta = gift_resolve(r.get('gift_name', '')) or {}
        except Exception:
            meta = {}
        recent.append({
            'user': display_user(r) or '@?',
            'gift': r.get('gift_name') or 'Gift',
            'count': r.get('gift_count', 1),
            'coins': r.get('gift_coins') or meta.get('coins', 0) or r.get('diamond_count', 0),
            'image': r.get('gift_image_url') or meta.get('image_url', ''),
            'avatar': str(r.get('avatar_url','') or ''),
            'cls': 'normal',
        })

    joins = []
    for row in db.joins(sid, 50):
        r = record_dict(row)
        joins.append({
            'rank': '', 'user': display_user(r) or '@?',
            'value': str(r.get('ts', ''))[11:19], 'cls': 'normal',
            'avatar': str(r.get('avatar_url','') or ''),
        })

    return {
        'viewers': int(stats.get('viewers', 0) or 0),
        'max': int(stats.get('max', 0) or 0),
        'chat': chat,
        'gifts': gifts,
        'recent-gifts': recent,
        'likes': likes,
        'followers': followers,
        'joins': joins,
    }
