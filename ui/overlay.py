from PySide6.QtCore import Qt, Signal, QPoint, QEvent, QTimer, QSize, QRectF
from PySide6.QtGui import QColor, QFontMetrics, QPainter, QPen, QIcon, QPixmap, QPainterPath, QFont, QTextDocument
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QListWidget, QFrame, QSlider,
    QHBoxLayout, QPushButton, QSizeGrip, QListWidgetItem, QDialog, QSizePolicy
)


class ResponsiveList(QListWidget):
    """Item-widget kullanan overlay listeleri için güvenli, responsive QListWidget.

    Önceki sürümde resizeEvent, QListWidgetItem.text() üzerinden yükseklik
    hesaplıyordu. setItemWidget() ile kullanılan satırlarda item.text() boş olduğu
    için uzun yorumların yüksekliği 30-44px'e düşüyor ve satırlar birbirinin
    üstüne biniyordu. Burada yalnızca viewport genişliği değişimini bildiriyoruz;
    gerçek satır yüksekliğini OverlayRowWidget hesaplıyor.
    """
    viewportResized = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWordWrap(True)
        self.setTextElideMode(Qt.ElideNone)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollMode(QListWidget.ScrollPerPixel)
        self.setUniformItemSizes(False)
        self.setSpacing(2)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        width = max(120, self.viewport().width())
        # Layout tamamlandıktan sonra ölçmek, scrollbar oluştuğunda da doğru
        # genişliği kullanmamızı sağlar.
        QTimer.singleShot(0, lambda w=width: self.viewportResized.emit(w))



class HeartBurst(QWidget):
    """OBS-safe kalp animasyonu. Native child-window/windowOpacity kullanmaz."""
    def __init__(self, parent):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setFixedSize(96, 96)
        self._step = 0
        self._timer = QTimer(self)
        self._timer.setInterval(30)
        self._timer.timeout.connect(self._tick)
        self.hide()

    def play(self):
        parent = self.parentWidget()
        if not parent:
            return
        self._step = 0
        self.move(parent.rect().center() - QPoint(self.width() // 2, self.height() // 2))
        self.raise_()
        self.show()
        self._timer.start()
        self.update()

    def _tick(self):
        self._step += 1
        if self._step >= 26:
            self._timer.stop()
            self.hide()
            return
        self.update()

    def paintEvent(self, event):
        if not self.isVisible():
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        progress = self._step / 26.0
        scale = 0.72 + progress * 0.55
        alpha = int(255 * (1.0 - max(0.0, progress - 0.45) / 0.55))
        alpha = max(0, min(255, alpha))
        p.translate(self.width()/2, self.height()/2)
        p.scale(scale, scale)
        p.setPen(QPen(QColor(255, 255, 255, min(alpha, 220)), 2))
        p.setBrush(QColor(255, 70, 110, alpha))
        # Heart shape built from a smooth polygon; stays inside the same top-level
        # window, which avoids OBS transparent-window capture artifacts.
        from math import sin, cos, pi
        pts = []
        for i in range(101):
            t = 2*pi*i/100.0
            x = 16 * sin(t)**3
            y = -(13*cos(t) - 5*cos(2*t) - 2*cos(3*t) - cos(4*t))
            pts.append(QPoint(int(x*1.65), int(y*1.65)))
        p.drawPolygon(pts)
        p.end()


class ImagePreview(QDialog):
    """Large avatar/image preview for local cache files or remote URLs."""
    def __init__(self, path_or_url, title='Görsel', parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(500,500)
        self.setMinimumSize(340,340)
        self._original_pixmap=QPixmap()
        self._source_meta={}
        self.setStyleSheet('QDialog{background:#0b0f16;color:white;} QLabel{color:white;background:transparent;}')
        box=QVBoxLayout(self); box.setContentsMargins(14,14,14,14)
        self.image=QLabel('Görsel yükleniyor...')
        self.image.setAlignment(Qt.AlignCenter)
        self.image.setMinimumSize(300,300)
        self.image.setStyleSheet('background:#080c12;border:1px solid rgba(255,255,255,35);border-radius:14px;')
        box.addWidget(self.image,1)
        self.info=QLabel('')
        self.info.setAlignment(Qt.AlignCenter)
        self.info.setStyleSheet('color:#91a3bb;font-size:12px;padding:2px;')
        box.addWidget(self.info)
        self._load_source(path_or_url)

    def _load_source(self, path_or_url):
        source=str(path_or_url or '').strip()
        try:
            from pathlib import Path
            import requests
            pix=QPixmap()
            local=Path(source).expanduser() if source else None
            if local and local.is_file():
                # Load bytes so Qt can sniff PNG/JPEG/WebP content regardless of extension.
                pix.loadFromData(local.read_bytes())
                if pix.isNull():
                    pix=QPixmap(str(local))
                # HQ avatar cache has a sidecar JSON containing the real upstream
                # dimensions. Never label an upscaled 100px source as native 1080.
                try:
                    import json
                    stem=local.stem.replace('_upscaled','')
                    meta_path=local.with_name(stem+'.json')
                    if meta_path.is_file():
                        self._source_meta=json.loads(meta_path.read_text(encoding='utf-8'))
                except Exception:
                    self._source_meta={}
            elif source.lower().startswith(('http://','https://')):
                r=requests.get(source,headers={'User-Agent':'Mozilla/5.0'},timeout=10)
                r.raise_for_status()
                pix.loadFromData(r.content)
            elif source:
                pix=QPixmap(source)
            if pix.isNull():
                self.image.setText('Profil fotoğrafı yüklenemedi.')
                self.image.setToolTip(source)
                return
            self._set_pix(pix)
        except Exception as exc:
            self.image.setText('Profil fotoğrafı yüklenemedi.')
            self.image.setToolTip(f'{source}\n{type(exc).__name__}: {exc}')

    def _set_pix(self,pix):
        if pix.isNull():
            self.image.setText('Görsel bulunamadı')
            return
        # Büyük profil penceresinde her zaman 1080x1080 çalışma görseli kullan.
        # Upstream yalnızca 72x72 döndürürse gerçek detay artmaz; ancak pencere artık
        # 72px pixmap'i doğrudan büyütmek yerine kaliteli SmoothTransformation ile
        # hazırlanmış sabit 1080x1080 önizlemeyi küçülterek gösterir.
        src_w, src_h = int(pix.width()), int(pix.height())
        target_px = 1080
        scaled = pix.scaled(target_px, target_px, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        x=max(0,(scaled.width()-target_px)//2)
        y=max(0,(scaled.height()-target_px)//2)
        preview=scaled.copy(x,y,target_px,target_px)
        self._original_pixmap=QPixmap(preview)
        meta=self._source_meta if isinstance(self._source_meta,dict) else {}
        real_w=int(meta.get('source_width') or src_w)
        real_h=int(meta.get('source_height') or src_h)
        native=bool(meta.get('native_1080')) or min(real_w,real_h)>=1080
        if native:
            self.info.setText(f'Native kaynak: {real_w} × {real_h} px  •  Önizleme: 1080 × 1080 px')
            self.info.setStyleSheet('color:#63e6a3;font-size:12px;padding:2px;')
        else:
            self.info.setText(f'Euler native 1080 bulunamadı • En yüksek kaynak: {real_w} × {real_h} px • Çıktı: 1080 × 1080 px')
            self.info.setStyleSheet('color:#ffc76b;font-size:12px;padding:2px;')
        self._render_pixmap()

    def _render_pixmap(self):
        if self._original_pixmap.isNull():
            return
        target=self.image.size()
        if target.width()<2 or target.height()<2:
            return
        self.image.setPixmap(self._original_pixmap.scaled(target,Qt.KeepAspectRatio,Qt.SmoothTransformation))

    def resizeEvent(self,e):
        super().resizeEvent(e)
        self._render_pixmap()

class ClickableAvatar(QLabel):
    def __init__(self, source, parent=None, size=38):
        super().__init__(parent); self.source=source; self._size=max(20,int(size)); self.setFixedSize(self._size,self._size); self.setAlignment(Qt.AlignCenter); self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet(f'border-radius:{self._size//2}px;background:rgba(255,255,255,20);')
        try:
            pix=QPixmap(str(source))
            if not pix.isNull(): self.setPixmap(self._circle_pixmap(pix,self._size-2))
            else: self.setText('👤')
        except Exception: self.setText('👤')

    @staticmethod
    def _circle_pixmap(pix, size):
        size=max(18,int(size)); target=QPixmap(size,size); target.fill(Qt.transparent)
        src=pix.scaled(size,size,Qt.KeepAspectRatioByExpanding,Qt.SmoothTransformation)
        sx=max(0,(src.width()-size)//2); sy=max(0,(src.height()-size)//2); src=src.copy(sx,sy,size,size)
        painter=QPainter(target); painter.setRenderHint(QPainter.Antialiasing,True)
        path=QPainterPath(); path.addEllipse(QRectF(0,0,size,size)); painter.setClipPath(path); painter.drawPixmap(0,0,src); painter.end(); return target

    def mousePressEvent(self,e):
        if e.button()==Qt.LeftButton and self.source:
            ImagePreview(self.source,'Görsel',self.window()).exec()
        super().mousePressEvent(e)


class OverlayRowWidget(QWidget):
    """Avatar + çok satırlı metin satırı.

    QListWidget.setItemWidget() satırlarının yüksekliğini içerikten ve mevcut
    viewport genişliğinden hesaplar. Böylece uzun chat mesajları avatarın veya
    bir sonraki mesajın üzerine taşmaz.
    """
    def __init__(self, text, color='#ffffff', avatar='', gift_image='', parent=None):
        super().__init__(parent)
        self._text = str(text or '')
        self._avatar_size = 38
        self._gift_size = 38
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(6, 5, 6, 5)
        self._layout.setSpacing(8)
        self._layout.setAlignment(Qt.AlignTop)

        self.avatar_widget = None
        self.gift_widget = None
        if avatar:
            self.avatar_widget = ClickableAvatar(avatar, self, self._avatar_size)
            self._layout.addWidget(self.avatar_widget, 0, Qt.AlignTop)
        elif gift_image:
            self.gift_widget = ClickableAvatar(gift_image, self, self._gift_size)
            self._layout.addWidget(self.gift_widget, 0, Qt.AlignTop)

        self.label = QLabel(self._text, self)
        self.label.setTextFormat(Qt.PlainText)
        self.label.setWordWrap(True)
        self.label.setTextInteractionFlags(Qt.NoTextInteraction)
        self.label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.label.setMinimumWidth(1)
        self.label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.label.setStyleSheet(
            f'color:{color}; background:transparent; font-size:14px; padding:1px 0px;'
        )
        self._layout.addWidget(self.label, 1, Qt.AlignTop)

        if avatar and gift_image:
            self.gift_widget = ClickableAvatar(gift_image, self, self._gift_size)
            self._layout.addWidget(self.gift_widget, 0, Qt.AlignTop)

        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)

    def _measure_text_height(self, label_width):
        """QLabel word-wrap yüksekliğini güvenli biçimde ölç.

        QFontMetrics.boundingRect bazı Windows/Segoe UI/emoji kombinasyonlarında
        son satırı birkaç piksel eksik hesaplayabiliyor. QTextDocument gerçek
        satır kırılımlarını ve font yüksekliğini kullanır; sonuna eklenen güvenlik
        payı da Windows DPI ölçeklemesinde alt satırın kırpılmasını engeller.
        """
        label_width = max(70, int(label_width))
        doc = QTextDocument()
        doc.setDefaultFont(self.label.font())
        doc.setDocumentMargin(0)
        doc.setPlainText(self._text)
        doc.setTextWidth(label_width)
        text_h = int(doc.size().height() + 0.999)
        fm = QFontMetrics(self.label.font())
        return max(fm.height(), text_h) + 10

    def height_for_width(self, width):
        width = max(120, int(width))
        margins = self._layout.contentsMargins()
        visible_fixed = []
        if self.avatar_widget is not None:
            visible_fixed.append(self.avatar_widget.width())
        if self.gift_widget is not None:
            visible_fixed.append(self.gift_widget.width())
        # Avatar/görsel ile label arasındaki layout spacing'lerini hesaba kat.
        gaps = self._layout.spacing() * len(visible_fixed)
        label_width = max(70, width - margins.left() - margins.right() - sum(visible_fixed) - gaps - 14)
        text_h = self._measure_text_height(label_width)
        # QLabel'in kendi layout hesabı item yüksekliğini tekrar küçültmesin.
        self.label.setMinimumHeight(text_h)
        media_h = max(visible_fixed) if visible_fixed else 0
        return max(48, media_h + margins.top() + margins.bottom() + 4, text_h + margins.top() + margins.bottom() + 8)

    def sizeHint(self):
        parent_width = self.parentWidget().width() if self.parentWidget() else 360
        return QSize(max(120, parent_width), self.height_for_width(parent_width))


class ChatRoleRowWidget(QWidget):
    """TikTok-style chat row: round avatar, compact role/rank badges, name and wrapped message."""
    ROLE_STYLES = {
        'publisher': ('🎤 Yayıncı', '#7a3fd0', '#ffffff'),
        'moderator': ('🛡️ Moderatör', '#287ed8', '#ffffff'),
        'subscriber': ('⭐ Abone', '#2a9d61', '#ffffff'),
        'love': ('🧡 Beni Sev', '#dd7a15', '#ffffff'),
        'normal': ('💬', '#5d6470', '#ffffff'),
    }
    GIFT_STYLES = {
        '🥇 Top 1': ('#e9b52f', '#171006'),
        '🥈 Top 2': ('#c6ccd4', '#15171a'),
        '🥉 Top 3': ('#c97a43', '#1a0d05'),
    }

    def __init__(self, row, parent=None):
        super().__init__(parent)
        self.row=dict(row or {})
        self._avatar_size=38
        self._root=QHBoxLayout(self)
        self._root.setContentsMargins(6,5,6,5)
        self._root.setSpacing(8)
        self._root.setAlignment(Qt.AlignTop)

        avatar=str(self.row.get('avatar','') or '')
        self.avatar_widget=None
        if avatar:
            self.avatar_widget=ClickableAvatar(avatar,self,self._avatar_size)
            self._root.addWidget(self.avatar_widget,0,Qt.AlignTop)

        body=QWidget(self)
        self._body=QVBoxLayout(body)
        self._body.setContentsMargins(0,0,0,0)
        self._body.setSpacing(3)

        header=QWidget(body)
        hb=QHBoxLayout(header)
        hb.setContentsMargins(0,0,0,0)
        hb.setSpacing(5)
        role=str(self.row.get('cls','normal') or 'normal')
        role_text,bg,fg=self.ROLE_STYLES.get(role,self.ROLE_STYLES['normal'])
        hb.addWidget(self._badge(role_text,bg,fg),0,Qt.AlignVCenter)
        gift_badge=str(self.row.get('badge','') or '')
        if gift_badge:
            gbg,gfg=self.GIFT_STYLES.get(gift_badge,('#6b7280','#ffffff'))
            hb.addWidget(self._badge(gift_badge,gbg,gfg),0,Qt.AlignVCenter)
        self.name=QLabel(str(self.row.get('user','@?') or '@?'),header)
        self.name.setStyleSheet(f"color:{self.row.get('color','#ffffff')};font-size:14px;font-weight:800;background:transparent;")
        self.name.setSizePolicy(QSizePolicy.Preferred,QSizePolicy.Fixed)
        hb.addWidget(self.name,0,Qt.AlignVCenter)
        hb.addStretch(1)
        self._body.addWidget(header)

        self.message=QLabel(str(self.row.get('message','') or ''),body)
        self.message.setTextFormat(Qt.PlainText)
        self.message.setWordWrap(True)
        self.message.setTextInteractionFlags(Qt.NoTextInteraction)
        self.message.setAlignment(Qt.AlignLeft|Qt.AlignTop)
        self.message.setMinimumWidth(1)
        self.message.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Preferred)
        self.message.setStyleSheet('color:#ffffff;background:transparent;font-size:14px;padding:0px;')
        self._body.addWidget(self.message)
        self._root.addWidget(body,1,Qt.AlignTop)
        self.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Minimum)

    @staticmethod
    def _badge(text,bg,fg):
        x=QLabel(str(text))
        x.setAlignment(Qt.AlignCenter)
        x.setSizePolicy(QSizePolicy.Fixed,QSizePolicy.Fixed)
        x.setStyleSheet(f'background:{bg};color:{fg};border-radius:5px;padding:2px 6px;font-size:11px;font-weight:900;')
        x.adjustSize()
        return x

    def height_for_width(self,width):
        width=max(150,int(width))
        margins=self._root.contentsMargins()
        avatar_w=self.avatar_widget.width()+self._root.spacing() if self.avatar_widget is not None else 0
        body_w=max(90,width-margins.left()-margins.right()-avatar_w-16)
        doc=QTextDocument(); doc.setDefaultFont(self.message.font()); doc.setDocumentMargin(0); doc.setPlainText(self.message.text()); doc.setTextWidth(body_w)
        msg_h=max(QFontMetrics(self.message.font()).height(),int(doc.size().height()+0.999))+6
        self.message.setMinimumHeight(msg_h)
        header_h=max(24,self.name.sizeHint().height()+4)
        media_h=self.avatar_widget.height() if self.avatar_widget is not None else 0
        content_h=header_h+self._body.spacing()+msg_h
        return max(54,media_h+margins.top()+margins.bottom()+4,content_h+margins.top()+margins.bottom()+8)

    def sizeHint(self):
        w=self.parentWidget().width() if self.parentWidget() else 380
        return QSize(max(150,w),self.height_for_width(w))


class AnimatedLikeText(QWidget):
    """Like row text with optional RGB and per-character wave animation."""
    def __init__(self,text,style,parent=None):
        super().__init__(parent); self.text=str(text); self.style={}; self.phase=0.0
        self.setMinimumHeight(34); self.setSizePolicy(self.sizePolicy().horizontalPolicy(), self.sizePolicy().verticalPolicy())
        self.timer=QTimer(self); self.timer.setInterval(45); self.timer.timeout.connect(self._tick)
        self.apply_style(style)

    def apply_style(self,style):
        self.style=dict(style or {})
        if self.style.get('wave_text') or self.style.get('rgb_text'):
            if not self.timer.isActive(): self.timer.start()
        else: self.timer.stop()
        self.update()

    def _tick(self):
        self.phase=(self.phase+0.24)%(6.28318*20); self.update()

    def sizeHint(self):
        fm=QFontMetrics(QFont('Segoe UI',11,QFont.Bold)); return QSize(max(150,fm.horizontalAdvance(self.text)+16),42)

    def paintEvent(self,event):
        from math import sin
        p=QPainter(self); p.setRenderHint(QPainter.Antialiasing,True); font=QFont('Segoe UI',11,QFont.Bold); p.setFont(font); fm=QFontMetrics(font)
        widths=[fm.horizontalAdvance(ch) for ch in self.text]; total=sum(widths); align=self.style.get('align','left')
        if align=='right': x=max(2,self.width()-total-4)
        elif align=='center': x=max(2,(self.width()-total)/2)
        else: x=4
        base=(self.height()+fm.ascent()-fm.descent())/2
        base_color=QColor(str(self.style.get('text_color','#ff5b7f'))); base_color=base_color if base_color.isValid() else QColor('#ff5b7f')
        wave=bool(self.style.get('wave_text')); rainbow=bool(self.style.get('rgb_text')); glow=bool(self.style.get('glow_text'))
        for i,ch in enumerate(self.text):
            y=base+(sin(self.phase+i*0.55)*3.5 if wave else 0)
            color=QColor.fromHsv(int((self.phase*45+i*13)%360),210,255) if rainbow else base_color
            if glow:
                p.setPen(QColor(color.red(),color.green(),color.blue(),70)); p.drawText(int(x+1),int(y+1),ch)
            p.setPen(color); p.drawText(int(x),int(y),ch); x+=widths[i]
        p.end()


class PulseHeartLabel(QLabel):
    def __init__(self,color='#ff2f67',parent=None):
        super().__init__('♥',parent); self.color=color; self.step=0; self.setAlignment(Qt.AlignCenter); self.setFixedWidth(30)
        self.timer=QTimer(self); self.timer.setInterval(95); self.timer.timeout.connect(self._tick); self.timer.start(); self._apply()
    def set_color(self,color): self.color=color; self._apply()
    def _tick(self): self.step=(self.step+1)%12; self._apply()
    def _apply(self):
        from math import sin,pi
        size=17+int((sin(self.step/12*pi*2)+1)*2.2); self.setStyleSheet(f'color:{self.color};font-size:{size}px;font-weight:900;background:transparent;')

class LikeCountLabel(QLabel):
    """Dedicated static label for like counts.

    Keeping the count outside AnimatedLikeText prevents RGB/wave name effects from
    accidentally overriding the separately selected count colour.
    """
    def __init__(self,text,color='#ffffff',glow=False,parent=None):
        super().__init__(str(text),parent)
        self.setAlignment(Qt.AlignVCenter | Qt.AlignRight)
        self.setSizePolicy(QSizePolicy.Fixed,QSizePolicy.Preferred)
        self.apply_color(color,glow)

    def apply_color(self,color,glow=False):
        c=QColor(str(color or '#ffffff'))
        if not c.isValid(): c=QColor('#ffffff')
        # QLabel stylesheet is explicit and independent from the animated username.
        self.setStyleSheet(f'color:{c.name()};font-size:14px;font-weight:800;background:transparent;padding:0 2px;')
        self.adjustSize()

class Overlay(QWidget):
    """OBS/yayın üzerinde kullanılabilen, saydam ve yeniden boyutlandırılabilir pencere."""
    closed = Signal()
    pinChanged = Signal(bool)
    backRequested = Signal()

    def __init__(self, title):
        super().__init__()
        self.setWindowTitle(title)
        self.resize(430, 500)
        self.setMinimumSize(280, 220)
        # Windows'ta background-only alpha için top-level surface de translucent olmalı.
        # Pencere custom frameless olarak kalır; başlangıçta %100 opaktır.
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.Window | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setAutoFillBackground(False)
        self.setMouseTracking(True)

        self._background_alpha = 0
        self._drag_pos = None
        self._resize_start = None
        self._resize_geom = None
        self._resize_edges = set()
        self._edge = 14
        self._pinned = True
        self._framed = True
        self._heart = None

        self.frame = QFrame()
        self.frame.setObjectName('frame')
        self._apply_style()

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.addWidget(self.frame)

        box = QVBoxLayout(self.frame)
        box.setContentsMargins(8, 8, 8, 8)
        box.setSpacing(5)

        self.header = QWidget()
        self.header.setCursor(Qt.OpenHandCursor)
        self.header.setAttribute(Qt.WA_StyledBackground, True)
        self.header.setStyleSheet('background: transparent;')
        header_box = QHBoxLayout(self.header)
        header_box.setContentsMargins(2, 2, 2, 2)
        header_box.setSpacing(6)

        self.title = QLabel(title)
        self.title.setObjectName('overlayTitle')
        self.title.setToolTip('Taşımak için başlık alanını sürükleyin.')
        header_box.addWidget(self.title)
        header_box.addStretch()

        self.alpha = QSlider(Qt.Horizontal)
        self.alpha.setRange(0, 100)
        self.alpha.setValue(100)
        self.alpha.setFixedWidth(58)
        self.alpha.setToolTip('Arka plan: 0 = saydam, 100 = opak. Yazılar ve avatarlar opak kalır.')
        self.alpha.valueChanged.connect(self.apply_alpha)
        header_box.addWidget(self.alpha)

        self.pin = QPushButton('📌')
        self.pin.setCheckable(True)
        self.pin.setChecked(True)
        self.pin.setToolTip('Her zaman üstte / normal pencere sırası')
        self.pin.clicked.connect(self.toggle_pin)
        self.pin.setFixedWidth(30)
        header_box.addWidget(self.pin)

        self.back = QPushButton('⬇')
        self.back.setToolTip('Pencereyi arkaya gönder')
        self.back.clicked.connect(self.send_back)
        self.back.setFixedWidth(30)
        header_box.addWidget(self.back)

        self.mode = QPushButton('OBS')
        self.mode.setToolTip('OBS görünür penceresi: normal başlık çubuğu / overlay görünümü')
        self.mode.clicked.connect(self.toggle_frame_mode)
        self.mode.setFixedWidth(40)
        header_box.addWidget(self.mode)

        self.close_btn = QPushButton('✕')
        self.close_btn.setToolTip('Pencereyi kapat')
        self.close_btn.clicked.connect(self.close_overlay)
        self.close_btn.setFixedWidth(30)
        header_box.addWidget(self.close_btn)
        box.addWidget(self.header)

        self.header.installEventFilter(self)
        self.title.installEventFilter(self)

        self.list = ResponsiveList()
        self.list.setSelectionMode(QListWidget.NoSelection)
        self.list.setMouseTracking(True)
        self.list.viewportResized.connect(self._reflow_rows)
        box.addWidget(self.list, 1)

        # Tutamaç + görünür boyutlandırma alanı. Ayrıca pencerenin dört kenarında
        # manuel resize desteği bulunduğu için küçük tutamaç şart değil.
        grip_row = QHBoxLayout()
        grip_row.setContentsMargins(0, 0, 0, 0)
        grip_row.addStretch()
        self.size_label = QLabel('↘ Boyutlandır')
        self.size_label.setToolTip('Sağ alt köşeyi sürükleyerek boyutlandırın')
        self.size_label.setStyleSheet('color: rgba(255,255,255,180); background: transparent;')
        grip_row.addWidget(self.size_label)
        self.resize_grip = QSizeGrip(self)
        self.resize_grip.setFixedSize(22, 22)
        self.resize_grip.setToolTip('Boyutlandırmak için sürükleyin')
        grip_row.addWidget(self.resize_grip, 0, Qt.AlignRight | Qt.AlignBottom)
        box.addLayout(grip_row)

        self._heart = HeartBurst(self.list)
        self._heart.hide()
        self.mode.setText('OBS')
        self.mode.setToolTip('OBS saydam modunu aç / kapat')
        # Slider artık hem normal hem OBS modunda arka plan şeffaflığını değiştirir.
        self.alpha.setEnabled(True)
        self.apply_alpha(self.alpha.value())

    def _apply_style(self):
        self.setStyleSheet('''
            QFrame#frame { background: transparent; border: 1px solid transparent; border-radius: 16px; }
            QLabel#overlayTitle { color: white; font-size: 15px; font-weight: 700; background: transparent; }
            QListWidget { background: transparent; color: white; border: 0; padding: 4px; font-size: 14px; outline: none; }
            QListWidget::item { color: white; padding: 0px; margin: 0px; background: transparent; border: 0; }
            QListWidget::item:hover { background: rgba(255,255,255,18); border-radius: 6px; }
            QPushButton { background: rgba(20,25,32,190); color: white; border: 1px solid rgba(255,255,255,70); padding: 5px 8px; border-radius: 6px; }
            QPushButton:hover { background: rgba(40,48,60,235); }
            QPushButton:checked { background: rgba(45,125,80,235); }
            QSlider::groove:horizontal { height: 4px; background: rgba(255,255,255,90); border-radius: 2px; }
            QSlider::handle:horizontal { width: 12px; margin: -4px 0; border-radius: 6px; background: rgb(90,190,255); }
        ''')

    def toggle_pin(self, checked=None):
        self._pinned = self.pin.isChecked() if checked is None else bool(checked)
        self.pin.setChecked(self._pinned)
        self.pin.setText('📌' if self._pinned else '📍')
        flags = self.windowFlags()
        if self._pinned:
            flags |= Qt.WindowStaysOnTopHint
        else:
            flags &= ~Qt.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.show()
        if self._pinned:
            self.raise_()
        self.pinChanged.emit(self._pinned)

    def send_back(self):
        self._pinned = False
        self.pin.setChecked(False)
        self.pin.setText('📍')
        flags = self.windowFlags() & ~Qt.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.show()
        self.lower()
        self.backRequested.emit()

    def toggle_frame_mode(self):
        # Windows'ta WA_TranslucentBackground/FramelessWindowHint'i çalışma anında
        # açıp kapatmak alpha kanalını bozabiliyor. Bu yüzden native surface sabit.
        self._framed = not self._framed
        if self._framed:
            self.mode.setText('OBS')
            self.mode.setToolTip('OBS temiz görünümüne geç')
            self.size_label.setVisible(True)
            self.resize_grip.setVisible(True)
        else:
            self.mode.setText('NORMAL')
            self.mode.setToolTip('Normal mini pencere görünümüne dön')
            self.size_label.setVisible(False)
            self.resize_grip.setVisible(False)
        self.alpha.setEnabled(True)
        self.apply_alpha(self.alpha.value())
        self.show()
        if self._pinned:
            self.raise_()
        QTimer.singleShot(0, lambda: self.apply_alpha(self.alpha.value()))

    def close_overlay(self):
        self.close()

    def closeEvent(self, event):
        self.closed.emit()
        event.accept()

    def toggle_overlay_mode(self):
        self.toggle_frame_mode()

    def eventFilter(self, obj, event):
        if obj in (self.header, self.title):
            if event.type() == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
                self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
                self.header.setCursor(Qt.ClosedHandCursor)
                event.accept(); return True
            if event.type() == QEvent.MouseMove and self._drag_pos:
                self.move(event.globalPosition().toPoint() - self._drag_pos)
                event.accept(); return True
            if event.type() == QEvent.MouseButtonRelease:
                self._drag_pos = None
                self.header.setCursor(Qt.OpenHandCursor)
                event.accept(); return True
        return super().eventFilter(obj, event)

    def _edge_at(self, pos):
        edges = set()
        if pos.x() <= self._edge: edges.add('left')
        if pos.x() >= self.width() - self._edge: edges.add('right')
        if pos.y() <= self._edge: edges.add('top')
        if pos.y() >= self.height() - self._edge: edges.add('bottom')
        return edges

    def _cursor_for_edges(self, edges):
        if edges in ({'left'}, {'right'}): return Qt.SizeHorCursor
        if edges in ({'top'}, {'bottom'}): return Qt.SizeVerCursor
        if edges in ({'left','top'}, {'right','bottom'}): return Qt.SizeFDiagCursor
        if edges in ({'right','top'}, {'left','bottom'}): return Qt.SizeBDiagCursor
        return Qt.ArrowCursor

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            return super().mousePressEvent(event)
        pos = event.position().toPoint()
        edges = self._edge_at(pos)
        if edges:
            self._resize_edges = edges
            self._resize_start = event.globalPosition().toPoint()
            self._resize_geom = self.geometry()
            event.accept(); return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        pos = event.position().toPoint()
        if self._resize_start and self._resize_edges:
            delta = event.globalPosition().toPoint() - self._resize_start
            g = self._resize_geom
            left, top, width, height = g.x(), g.y(), g.width(), g.height()
            minw, minh = self.minimumWidth(), self.minimumHeight()
            if 'left' in self._resize_edges:
                new_left = min(left + delta.x(), left + width - minw)
                left = new_left; width = g.right() - new_left + 1
            if 'right' in self._resize_edges: width = max(minw, width + delta.x())
            if 'top' in self._resize_edges:
                new_top = min(top + delta.y(), top + height - minh)
                top = new_top; height = g.bottom() - new_top + 1
            if 'bottom' in self._resize_edges: height = max(minh, height + delta.y())
            self.setGeometry(left, top, width, height)
            event.accept(); return
        edges = self._edge_at(pos)
        self.setCursor(self._cursor_for_edges(edges))
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        self._resize_start = None
        self._resize_geom = None
        self._resize_edges = set()
        self.setCursor(Qt.ArrowCursor)
        super().mouseReleaseEvent(event)

    def apply_alpha(self, value):
        # 0-100 yalnızca frame arka planını etkiler; setWindowOpacity kullanılmaz.
        pct = max(0, min(100, int(value)))
        self._background_alpha = round(pct * 255 / 100)
        bg_alpha = self._background_alpha
        border_alpha = (120 if pct > 0 else 0) if self._framed else min(105, max(0, int(bg_alpha * 0.45)))
        bg = 'transparent' if bg_alpha <= 0 else f'rgba(10,14,20,{bg_alpha})'
        border = 'transparent' if border_alpha <= 0 else f'rgba(255,255,255,{border_alpha})'
        self.frame.setAttribute(Qt.WA_StyledBackground, True)
        self.frame.setStyleSheet(
            'QFrame#frame { background-color: %s; border: 1px solid %s; border-radius: 16px; }'
            'QLabel#overlayTitle { color: white; font-size: 15px; font-weight: 700; background: transparent; }'
            % (bg, border)
        )
        self.frame.update()
        self.update()

    def _reflow_rows(self, viewport_width=None):
        """Tüm item-widget satırlarını mevcut genişliğe göre yeniden ölç."""
        if not hasattr(self, 'list'):
            return
        width = max(120, int(viewport_width or self.list.viewport().width()) - 4)
        for i in range(self.list.count()):
            item = self.list.item(i)
            widget = self.list.itemWidget(item)
            if widget is None:
                continue
            if hasattr(widget, 'height_for_width'):
                height = int(widget.height_for_width(width))
                widget.setMinimumHeight(height)
                widget.updateGeometry()
                item.setSizeHint(QSize(width, height))
            else:
                hint = widget.sizeHint()
                item.setSizeHint(QSize(width, max(36, item.sizeHint().height(), hint.height())))
        self.list.doItemsLayout()
        self.list.viewport().update()

    def set_rows(self, rows, colors=None):
        """Rows can be text, (text, avatar), or (text, avatar, gift_image)."""
        colors = colors or []
        normalized=[]
        for row in rows:
            if isinstance(row,(tuple,list)):
                normalized.append((str(row[0]),str(row[1] or '') if len(row)>1 else '',str(row[2] or '') if len(row)>2 else ''))
            else:
                normalized.append((str(row),'',''))

        self.list.setUpdatesEnabled(False)
        self.list.clear()
        width = max(120, self.list.viewport().width() - 4)
        for i,(text,avatar,gift_image) in enumerate(normalized):
            color = colors[i].name() if i < len(colors) else '#ffffff'
            item = QListWidgetItem()
            widget = OverlayRowWidget(text, color, avatar, gift_image, self.list)
            row_height = widget.height_for_width(width)
            widget.setMinimumHeight(row_height)
            item.setSizeHint(QSize(width, row_height))
            self.list.addItem(item)
            self.list.setItemWidget(item, widget)
        self.list.setUpdatesEnabled(True)
        self._reflow_rows(width)
        # İlk gösterimde font/layout metrikleri bir event-loop turu sonra kesinleşir.
        QTimer.singleShot(0, self._reflow_rows)
        QTimer.singleShot(40, self._reflow_rows)

    def play_heart(self):
        if self._heart:
            self._heart.raise_()
            self._heart.play()


class ChatOverlay(Overlay):
    def __init__(self):
        super().__init__('💬 LIVE CHAT')
        self._auto_scroll = True

    def set_rows(self, rows, colors=None):
        if rows and isinstance(rows[0],dict):
            self.list.setUpdatesEnabled(False)
            self.list.clear()
            width=max(140,self.list.viewport().width()-4)
            for row in rows:
                item=QListWidgetItem()
                widget=ChatRoleRowWidget(row,self.list)
                h=widget.height_for_width(width)
                widget.setMinimumHeight(h)
                item.setSizeHint(QSize(width,h))
                self.list.addItem(item)
                self.list.setItemWidget(item,widget)
            self.list.setUpdatesEnabled(True)
            self.list.viewport().update()
        else:
            super().set_rows(rows, colors)
        if self._auto_scroll:
            QTimer.singleShot(0, self._scroll_bottom)
            QTimer.singleShot(35, self._scroll_bottom)

    def _scroll_bottom(self):
        self.list.scrollToBottom()

class StyledListOverlay(Overlay):
    """Gift/follower widgets with the same visual customization model as likes."""
    def __init__(self,title,default_color='#ffffff'):
        super().__init__(title)
        self.list_style={'align':'left','text_color':default_color,'rgb_text':False,'wave_text':False,'glow_text':False,'avatar_size':34,'row_gap':6,'show_avatar':True,'show_title':True,'bg_alpha':48}

    def apply_list_style(self,style):
        self.list_style.update(style or {})
        self.title.setVisible(bool(self.list_style.get('show_title',True)))
        self.list.setSpacing(int(self.list_style.get('row_gap',6) if self.list_style.get('row_gap',6) is not None else 6))
        # Browser Source bg_alpha mini pencere sliderından bağımsızdır.

    def set_styled_rows(self,rows):
        self.list.setUpdatesEnabled(False); self.list.clear(); style=dict(self.list_style); align=style.get('align','left')
        for idx,row in enumerate(rows or []):
            item=QListWidgetItem(); widget=QWidget(); hb=QHBoxLayout(widget); hb.setContentsMargins(7,4,7,4); hb.setSpacing(int(style.get('row_gap',6) if style.get('row_gap',6) is not None else 6))
            if idx==0: widget.setStyleSheet('background:rgba(255,255,255,18);border-radius:8px;')
            if align in ('right','center'): hb.addStretch(1)
            avatar=str(row.get('avatar','') or '')
            if style.get('show_avatar',True) and avatar: hb.addWidget(ClickableAvatar(avatar,widget,int(style.get('avatar_size',34) or 34)))
            image=str(row.get('image','') or '')
            if image: hb.addWidget(ClickableAvatar(image,widget,34))
            label=AnimatedLikeText(str(row.get('text','')),style,widget); hb.addWidget(label,1 if align=='left' else 0)
            if align=='center': hb.addStretch(1)
            item.setSizeHint(QSize(max(160,self.list.viewport().width()),max(46,int(style.get('avatar_size',34) or 34)+10)))
            self.list.addItem(item); self.list.setItemWidget(item,widget)
        self.list.setUpdatesEnabled(True); self.list.viewport().update()

    def set_rows(self, rows, colors=None):
        if rows and isinstance(rows[0],dict): self.set_styled_rows(rows)
        else: super().set_rows(rows,colors)

class GiftOverlay(StyledListOverlay):
    def __init__(self): super().__init__('🎁 TOP GIFTERLAR','#ffd166')
class RecentGiftOverlay(StyledListOverlay):
    def __init__(self): super().__init__('🎁 SON HEDİYELER','#ffd166')
class LikeOverlay(Overlay):
    def __init__(self):
        super().__init__('❤️ TOP BEĞENİ')
        self.like_style={'align':'left','text_color':'#ff5b7f','count_color':'#ffffff','heart_color':'#ff2f67','rgb_text':False,'wave_text':False,'glow_text':True,'avatar_size':34,'row_gap':6,'show_avatar':True,'show_title':True,'bg_alpha':48}

    def apply_like_style(self, style):
        self.like_style.update(style or {})
        self.title.setVisible(bool(self.like_style.get('show_title',True)))
        self.list.setSpacing(int(self.like_style.get('row_gap',6) if self.like_style.get('row_gap',6) is not None else 6))
        # Browser Source bg_alpha mini pencere sliderından bağımsızdır.

    def set_like_rows(self, rows):
        self.list.setUpdatesEnabled(False); self.list.clear(); style=dict(self.like_style); align=style.get('align','left')
        for idx,row in enumerate(rows or []):
            item=QListWidgetItem(); widget=QWidget(); hb=QHBoxLayout(widget); hb.setContentsMargins(7,4,7,4); hb.setSpacing(int(style.get('row_gap',6) if style.get('row_gap',6) is not None else 6))
            if idx==0: widget.setStyleSheet('background:rgba(255,255,255,18);border-radius:8px;')
            if align in ('right','center'): hb.addStretch(1)
            avatar=str(row.get('avatar','') or '')
            if style.get('show_avatar',True) and avatar: hb.addWidget(ClickableAvatar(avatar,widget,int(style.get('avatar_size',34) or 34)))
            prefix=f"{row.get('rank','')} {row.get('user','@?')} •"
            label=AnimatedLikeText(prefix,style,widget); hb.addWidget(label,1 if align=='left' else 0)
            count=LikeCountLabel(
                f"{int(row.get('likes',0) or 0):,}",
                str(style.get('count_color','#ffffff')),
                bool(style.get('glow_text',True)),
                widget
            )
            hb.addWidget(count)
            heart=PulseHeartLabel(str(style.get('heart_color','#ff2f67')),widget); hb.addWidget(heart)
            if align=='center': hb.addStretch(1)
            item.setSizeHint(QSize(max(160,self.list.viewport().width()),max(46,int(style.get('avatar_size',34) or 34)+10)))
            self.list.addItem(item); self.list.setItemWidget(item,widget)
        self.list.setUpdatesEnabled(True); self.list.viewport().update()

    def set_rows(self, rows, colors=None):
        # Backward compatible fallback for older callers/tests.
        if rows and isinstance(rows[0],dict): self.set_like_rows(rows)
        else: super().set_rows(rows,colors)
class FollowOverlay(StyledListOverlay):
    def __init__(self): super().__init__('👥 SON TAKİPÇİLER','#ffffff')
