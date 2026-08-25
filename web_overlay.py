import json
import threading
import socket
import html
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse


class BrowserOverlayServer:
    """Local OBS Browser Source server.

    URLs: /chat /gifts /recent-gifts /likes /followers /joins /viewers /all
    """
    def __init__(self, snapshot_cb, host='127.0.0.1', port=8765):
        self.snapshot_cb = snapshot_cb
        self.host = host
        self.port = int(port)
        self.server = None
        self.thread = None

    def start(self):
        if self.server:
            return self.port
        callback = self.snapshot_cb

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, fmt, *args):
                return

            def _send(self, body, content_type='text/html; charset=utf-8'):
                raw = body.encode('utf-8') if isinstance(body, str) else body
                self.send_response(200)
                self.send_header('Content-Type', content_type)
                self.send_header('Content-Length', str(len(raw)))
                self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(raw)

            def do_GET(self):
                path = urlparse(self.path).path
                if path.startswith('/api/'):
                    try:
                        data = callback()
                        key = path[5:]
                        if key != 'all':
                            data = data.get(key, {})
                        self._send(json.dumps(data, ensure_ascii=False), 'application/json; charset=utf-8')
                    except Exception as exc:
                        self._send(json.dumps({'error': f'{type(exc).__name__}: {exc}'}, ensure_ascii=False), 'application/json; charset=utf-8')
                    return
                if path == '/health':
                    self._send(json.dumps({'ok': True, 'port': self.server.server_address[1]}), 'application/json; charset=utf-8')
                    return
                routes = {
                    '/': ('TikTok LIVE', 'all'),
                    '/chat': ('LIVE Chat', 'chat'),
                    '/gifts': ('Top Gifters', 'gifts'),
                    '/recent-gifts': ('Recent Gifts', 'recent-gifts'),
                    '/likes': ('Top Likes', 'likes'),
                    '/followers': ('Followers', 'followers'),
                    '/joins': ('Joined', 'joins'),
                    '/viewers': ('Viewers', 'viewers'),
                    '/all': ('TikTok LIVE', 'all'),
                }
                if path in routes:
                    title, mode = routes[path]
                    self._send(page(title, mode))
                    return
                self.send_error(404)

        try:
            self.server = ThreadingHTTPServer((self.host, self.port), Handler)
        except OSError:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
                probe.bind((self.host, 0))
                self.port = probe.getsockname()[1]
            self.server = ThreadingHTTPServer((self.host, self.port), Handler)
        self.port = int(self.server.server_address[1])
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True, name='OBS-BrowserSource')
        self.thread.start()
        return self.port

    def stop(self):
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            self.server = None


def page(title, mode):
    template = r'''<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<style>
:root{--text:#fff;--like-text:#ff5b7f;--like-count:#ffffff;--heart:#ff2f67;--avatar:34px;--row-gap:6px;--bg:rgba(0,0,0,.48);--row-font:18px;--title-font:20px}
*{box-sizing:border-box}
html,body{margin:0;width:100%;height:100%;background:transparent;color:white;font-family:"Segoe UI","Segoe UI Emoji",Arial,sans-serif;overflow:hidden}
#box{position:relative;width:100%;height:100vh;display:flex;flex-direction:column;padding:12px;background:var(--bg);border:1px solid rgba(255,255,255,.10);border-radius:14px;text-shadow:0 2px 4px #000;overflow:hidden}
.title{font-size:var(--title-font);font-weight:800;margin-bottom:6px}
#content{display:flex;flex:1;min-height:0;flex-direction:column;gap:var(--row-gap);overflow:hidden}
.row{display:flex;gap:9px;align-items:flex-start;padding:6px 8px;font-size:var(--row-font);line-height:1.35;min-height:40px;flex:0 0 auto}
.row:first-child{background:rgba(255,255,255,.07);border-radius:8px}
.name{font-weight:700}.muted{opacity:.88}.num{font-weight:800;min-width:35px;white-space:nowrap}.chat-body{display:flex;flex-direction:column;min-width:0;flex:1}.chat-head{display:flex;align-items:center;gap:6px;flex-wrap:wrap}.chat-message{display:block;color:var(--text);word-break:break-word;overflow-wrap:anywhere;white-space:pre-wrap}
.badges{display:inline-flex;align-items:center;gap:4px;flex:0 0 auto;flex-wrap:wrap}.badge{display:inline-flex;align-items:center;justify-content:center;gap:5px;padding:3px 7px;border-radius:999px;font-size:12px;font-weight:900;line-height:1.25;color:#fff;text-shadow:none;white-space:nowrap;font-family:"Segoe UI Emoji","Segoe UI","Apple Color Emoji","Noto Color Emoji",sans-serif}.role-emoji,.gift-emoji{font-family:"Segoe UI Emoji","Apple Color Emoji","Noto Color Emoji",sans-serif;font-size:15px;line-height:1;display:inline-block;min-width:16px;text-align:center}.role-publisher{background:#7a3fd0}.role-moderator{background:#287ed8}.role-subscriber{background:#2a9d61}.role-love{background:#dd7a15}.role-normal{background:#5d6470}.gift-top1{background:linear-gradient(135deg,#bc7b00,#f6c343);color:#181005}.gift-top2{background:linear-gradient(135deg,#626b76,#d6dce2);color:#111}.gift-top3{background:linear-gradient(135deg,#8b4f24,#d78a50);color:#160b05}
.normal{color:#fff}.moderator{color:#ff4d4d}.love{color:#ff9f1a}.publisher{color:#b36bff}.subscriber{color:#32d583}
.card{font-size:34px;font-weight:800}
.avatar{width:var(--avatar);height:var(--avatar);border-radius:50%;object-fit:cover;object-position:center;flex:0 0 auto;border:1px solid rgba(255,255,255,.22);box-shadow:0 2px 8px rgba(0,0,0,.45)}
.gift-image{width:34px;height:34px;object-fit:contain;flex:0 0 auto}

.styled-list.align-left .row{justify-content:flex-start;text-align:left}
.styled-list.align-center .row{justify-content:center;text-align:center}
.styled-list.align-right .row{justify-content:flex-end;text-align:right}
.styled-text{font-weight:800;color:var(--text)}
.chat-feed{position:relative;display:block!important;overflow:hidden!important}
.chat-stack{position:absolute;left:0;right:0;bottom:0;display:flex;flex-direction:column;gap:var(--row-gap)}
.chat-row-enter{animation:chatRise .28s ease-out both}
@keyframes chatRise{from{opacity:0;transform:translateY(18px)}to{opacity:1;transform:translateY(0)}}
.like-list.align-left .row{justify-content:flex-start;text-align:left}
.like-list.align-center .row{justify-content:center;text-align:center}
.like-list.align-right .row{justify-content:flex-end;text-align:right}
.like-text{font-weight:800;color:var(--like-text);white-space:nowrap}
.like-count{font-weight:800;color:var(--like-count)!important;-webkit-text-fill-color:var(--like-count)!important;white-space:nowrap}
.like-heart{display:inline-block;color:var(--heart);font-size:20px;filter:drop-shadow(0 0 5px color-mix(in srgb,var(--heart) 70%, transparent));animation:heartPulse .78s ease-in-out infinite;transform-origin:center}
.glow{filter:drop-shadow(0 0 5px currentColor)}
.rgb-char{display:inline-block;animation:rgbShift 2.2s linear infinite}
.wave-char{display:inline-block;animation:waveChar 1.15s ease-in-out infinite;animation-delay:calc(var(--i) * -55ms)}
.rgb-char.wave-char{animation:rgbShift 2.2s linear infinite,waveChar 1.15s ease-in-out infinite;animation-delay:calc(var(--i) * -55ms),calc(var(--i) * -55ms)}
.float-heart{position:absolute;right:8%;bottom:8px;color:var(--heart);font-size:24px;pointer-events:none;animation:floatHeart 1.25s ease-out forwards;filter:drop-shadow(0 0 6px currentColor)}
@keyframes heartPulse{0%,100%{transform:scale(.90)}50%{transform:scale(1.22)}}
@keyframes waveChar{0%,100%{transform:translateY(0)}50%{transform:translateY(-5px)}}
@keyframes rgbShift{0%{color:#ff4d6d}20%{color:#ffd166}40%{color:#06d6a0}60%{color:#4cc9f0}80%{color:#b517ff}100%{color:#ff4d6d}}
@keyframes floatHeart{0%{opacity:0;transform:translate(0,8px) scale(.7)}15%{opacity:1}100%{opacity:0;transform:translate(-18px,-110px) scale(1.35)}}
</style></head>
<body><div id="box"><div class="title">__TITLE__</div><div id="content"></div></div>
<script>
const mode=__MODE__;
let lastLikeTotal=0;
let lastChatKey='';
function esc(s){return String(s??'').replace(/[&<>\"]/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;'}[m]))}
function cls(x){return x||'normal'}
function roleIcon(x){return ({publisher:'🎤',moderator:'🛡️',subscriber:'⭐',love:'🧡',normal:'💬'})[cls(x)]||'💬'}
function roleLabel(x){return ({publisher:'Yayıncı',moderator:'Moderatör',subscriber:'Abone',love:'Beni Sev',normal:'Normal Kullanıcı'})[cls(x)]||'Normal Kullanıcı'}
function giftBadgeClass(b){b=String(b||'');return b.includes('Top 1')?'gift-top1':(b.includes('Top 2')?'gift-top2':(b.includes('Top 3')?'gift-top3':''))}
function splitGiftBadge(b){b=String(b||'').trim();if(!b)return {emoji:'',label:''};if(b.includes('Top 1'))return {emoji:'🥇',label:'Top 1'};if(b.includes('Top 2'))return {emoji:'🥈',label:'Top 2'};if(b.includes('Top 3'))return {emoji:'🥉',label:'Top 3'};return {emoji:'🎁',label:b}}
function chatBadges(x){let roleCls=cls(x.cls);let roleEmoji=String(x.icon||roleIcon(roleCls)||'💬');let label=roleLabel(roleCls);let role=`<span class="badge role-${roleCls}" title="${esc(label)}"><span class="role-emoji">${esc(roleEmoji)}</span><span>${esc(label)}</span></span>`;let gb=splitGiftBadge(x.badge);let gift=gb.label?`<span class="badge ${giftBadgeClass(x.badge)}"><span class="gift-emoji">${esc(gb.emoji)}</span><span>${esc(gb.label)}</span></span>`:'';return `<span class="badges">${role}${gift}</span>`}
function avatar(x){return x&&x.avatar?`<img class="avatar" src="${esc(x.avatar)}" onerror="this.style.display='none'">`:''}
function safeColor(v,fallback){return /^#[0-9a-fA-F]{6}$/.test(String(v||''))?String(v):fallback}
function chars(text,wave,rgb){return Array.from(String(text??'')).map((ch,i)=>`<span class="${wave?'wave-char ':''}${rgb?'rgb-char':''}" style="--i:${i}">${esc(ch)}</span>`).join('')}
function applyStyle(style){
 style=style||{}; let root=document.documentElement.style;
 root.setProperty('--text',safeColor(style.text_color,'#ffffff'));
 root.setProperty('--like-text',safeColor(style.text_color,'#ff5b7f'));
 root.setProperty('--like-count',safeColor(style.count_color,'#ffffff'));
 root.setProperty('--heart',safeColor(style.heart_color,'#ff2f67'));
 root.setProperty('--avatar',Math.max(20,Math.min(80,Number(style.avatar_size||34)))+'px');
 root.setProperty('--row-gap',Math.max(0,Math.min(24,Number(style.row_gap||6)))+'px');
 let a=Math.max(0,Math.min(100,Number(style.bg_alpha??48)))/100; root.setProperty('--bg',`rgba(0,0,0,${a})`);
 root.setProperty('--row-font',Math.max(12,Math.min(42,Number(style.font_size||18)))+'px');
 root.setProperty('--title-font',Math.max(14,Math.min(44,Number(style.title_size||20)))+'px');
 let t=document.querySelector('.title'); if(t)t.style.display=style.show_title===false?'none':'';
}
function styledText(text,style){return `<span class="styled-text ${style.glow_text?'glow':''}">${chars(text,!!style.wave_text,!!style.rgb_text)}</span>`}
function spawnHearts(count){let box=document.getElementById('box'); for(let i=0;i<Math.min(8,count);i++){let h=document.createElement('span');h.className='float-heart';h.textContent='♥';h.style.right=(5+Math.random()*24)+'%';h.style.animationDelay=(i*45)+'ms';box.appendChild(h);setTimeout(()=>h.remove(),1500)}}
function render(d){
 let c=document.getElementById('content'); if(d&&d.error){c.innerHTML='<div class="muted">Veri hatası: '+esc(d.error)+'</div>';return}
 let styles=d.widget_styles||{}; let st=styles[mode]||d.widget_style||{}; applyStyle(st);
 if(mode==='viewers'){c.className='';c.innerHTML='<div class="card">👁 '+esc(d.viewers||0)+'</div><div class="muted">Maksimum: '+esc(d.max||0)+'</div>';return}
 let arr=d[mode]||[];
 if(mode==='all'){arr=(d.chat||[]).slice(-12);c.className='';c.innerHTML=arr.map(x=>`<div class="row">${avatar(x)}${chatBadges(x)}<span class="name ${cls(x.cls)}">${esc(x.user)}</span><span>${esc(x.message)}</span></div>`).join('')||'<div class="muted">Chat bekleniyor...</div>';return}
 if(mode==='chat'){
   c.className='chat-feed'; arr=arr.slice(-120);
   if(!arr.length){c.innerHTML='<div class="muted">Chat bekleniyor...</div>';lastChatKey='';return}
   let newest=arr[arr.length-1]; let key=`${newest.ts||''}|${newest.user||''}|${newest.message||''}`; let changed=!!lastChatKey&&key!==lastChatKey;
   c.innerHTML=`<div class="chat-stack">${arr.map((x,i)=>`<div class="row ${changed&&i===arr.length-1?'chat-row-enter':''}">${(st.show_avatar!==false)?avatar(x):''}<div class="chat-body"><div class="chat-head">${chatBadges(x)}<span class="name ${cls(x.cls)}">${esc(x.user)}</span></div><span class="chat-message">${esc(x.message)}</span></div></div>`).join('')}</div>`;
   lastChatKey=key; return;
 }
 if(mode==='recent-gifts'){
   c.className='styled-list align-'+(['left','center','right'].includes(st.align)?st.align:'left'); let showAvatar=st.show_avatar!==false;
   c.innerHTML=arr.map(x=>`<div class="row">${showAvatar?avatar(x):''}${x.image?`<img class="gift-image" src="${esc(x.image)}">`:''}${styledText(`${x.user} → ${x.gift} ×${x.count} • ${x.coins} 💎`,st)}</div>`).join('')||'<div class="muted">Hediye bekleniyor...</div>';return;
 }
 if(mode==='likes'){
   c.className='like-list align-'+(['left','center','right'].includes(st.align)?st.align:'left');
   let showAvatar=st.show_avatar!==false;
   let countColor=safeColor(st.count_color,'#ffffff');
   c.innerHTML=arr.map((x,i)=>{let count=Number(x.likes??String(x.value||'').replace(/\D/g,''))||0;let prefix=`${x.rank||i+1} ${x.user} •`;let styled=chars(prefix,!!st.wave_text,!!st.rgb_text);return `<div class="row">${showAvatar?avatar(x):''}<span class="like-text ${st.glow_text?'glow':''}">${styled}</span><span class="like-count ${st.glow_text?'glow':''}">${esc(count.toLocaleString())}</span><span class="like-heart">♥</span></div>`}).join('')||'<div class="muted">Beğeni bekleniyor...</div>';
   c.querySelectorAll('.like-count').forEach(el=>{el.style.setProperty('color',countColor,'important');el.style.setProperty('-webkit-text-fill-color',countColor,'important')});
   let total=arr.reduce((a,x)=>a+(Number(x.likes)||0),0);if(lastLikeTotal&&total>lastLikeTotal)spawnHearts(Math.max(1,Math.min(8,total-lastLikeTotal)));lastLikeTotal=total;return;
 }
 let useStyled=(mode==='gifts'||mode==='followers');
 if(useStyled){
   c.className='styled-list align-'+(['left','center','right'].includes(st.align)?st.align:'left'); let showAvatar=st.show_avatar!==false;
   c.innerHTML=arr.map((x,i)=>`<div class="row">${showAvatar?avatar(x):''}${styledText(`${x.rank?x.rank+' ':''}${x.user}${x.value?' • '+x.value:''}`,st)}</div>`).join('')||'<div class="muted">Veri bekleniyor...</div>';
 } else {
   c.className='';c.innerHTML=arr.map((x,i)=>`<div class="row">${avatar(x)}<span class="num">${x.rank?esc(x.rank):i+1}</span><span class="name ${cls(x.cls)}">${esc(x.user)}</span><span class="muted">${esc(x.value)}</span></div>`).join('')||'<div class="muted">Veri bekleniyor...</div>';
 }
}
async function tick(){try{let r=await fetch('/api/all?t='+Date.now(),{cache:'no-store'});let d=await r.json();render(d)}catch(e){document.getElementById('content').innerHTML='<div class="muted">Uygulama bağlantısı bekleniyor...</div>'}}
tick();setInterval(tick,450);
</script></body></html>'''
    return template.replace('__TITLE__', html.escape(str(title))).replace('__MODE__', json.dumps(mode, ensure_ascii=False))
