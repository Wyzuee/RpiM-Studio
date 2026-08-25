from datetime import datetime, timedelta

def since_for(mode):
    n = datetime.now()
    if mode == "Bugün":
        return n.replace(hour=0,minute=0,second=0,microsecond=0).isoformat(timespec="seconds")
    if mode == "Dün":
        d = n - timedelta(days=1)
        return d.replace(hour=0,minute=0,second=0,microsecond=0).isoformat(timespec="seconds")
    if mode == "Bu ay":
        return n.replace(day=1,hour=0,minute=0,second=0,microsecond=0).isoformat(timespec="seconds")
    if mode == "Bu yıl":
        return n.replace(month=1,day=1,hour=0,minute=0,second=0,microsecond=0).isoformat(timespec="seconds")
    return None
