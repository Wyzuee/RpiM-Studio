"""StreamToEarn TikTok gift catalog adapter.

The catalog is fetched from StreamToEarn's public Turkish gift page and cached locally.
If the site is temporarily unavailable, the application continues using LIVE event gift
metadata and the last cached catalog.
"""
from __future__ import annotations

import json, re, threading, time
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin
import requests

CATALOG_URL = "https://streamtoearn.io/tr/gifts?region=TR"

class _GiftParser(HTMLParser):
    def __init__(self):
        super().__init__(); self.items=[]; self._current_img=''; self._current_alt=''; self._texts=[]
    def _flush(self):
        if not self._current_img:return
        coins=0
        for t in self._texts:
            m=re.fullmatch(r'[\d,]+',t.replace(' ',''))
            if m:
                try: coins=int(m.group(0).replace(',',''))
                except ValueError: pass
                if coins: break
        self.items.append((self._current_alt,self._current_img,coins))
        self._current_img=''; self._current_alt=''; self._texts=[]
    def handle_starttag(self, tag, attrs):
        if tag.lower()=='img':
            a=dict(attrs); alt=str(a.get('alt') or ''); src=str(a.get('src') or a.get('data-src') or a.get('data-lazy-src') or '')
            if 'tiktok gift' in alt.lower() and src:
                self._flush(); self._current_img=src; self._current_alt=re.sub(r'\s+TikTok gift\s*$','',alt,flags=re.I).strip()
    def handle_data(self, data):
        if self._current_img:
            t=data.strip()
            if t:self._texts.append(t)
    def close(self):
        super().close(); self._flush()

class GiftCatalog:
    def __init__(self, base):
        self.path=Path(base)/'data'/'streamtoearn_gifts.json'; self.path.parent.mkdir(parents=True,exist_ok=True)
        self.lock=threading.RLock(); self.data={}; self.loading=False
        self._load_cache()
    def _load_cache(self):
        try:
            raw=json.loads(self.path.read_text(encoding='utf-8'))
            if isinstance(raw,dict): self.data=raw
        except Exception: self.data={}
    def start(self):
        if self.loading:return
        self.loading=True
        threading.Thread(target=self.refresh,daemon=True,name='GiftCatalog').start()
    def refresh(self):
        try:
            r=requests.get(CATALOG_URL,headers={'User-Agent':'Mozilla/5.0 RpiMStudio'},timeout=15)
            r.raise_for_status()
            p=_GiftParser(); p.feed(r.text)
            new={}
            for name,img,coins in p.items:
                if not name: continue
                key=name.casefold().strip()
                if key not in new or (coins and not new[key].get('coins')):
                    new[key]={'name':name,'image_url':urljoin(CATALOG_URL,img),'coins':int(coins or 0),'source':'StreamToEarn'}
            if new:
                with self.lock:
                    self.data.update(new)
                    self.path.write_text(json.dumps(self.data,ensure_ascii=False,indent=2),encoding='utf-8')
        except Exception:
            pass
        finally:self.loading=False
    def resolve(self,name):
        key=str(name or '').casefold().strip()
        with self.lock:
            return dict(self.data.get(key,{}))
