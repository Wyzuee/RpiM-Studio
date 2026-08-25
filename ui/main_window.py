from datetime import datetime
from pathlib import Path
from urllib.parse import quote, urlsplit, urlunsplit
import hashlib, random, re, threading, time, requests, json
from PySide6.QtCore import QObject, Signal, QTimer, Qt, QSize, QUrl
from PySide6.QtGui import QFont, QColor, QIcon, QDesktopServices, QPixmap
from PySide6.QtWidgets import (QApplication,QMainWindow,QWidget,QVBoxLayout,QHBoxLayout,QGridLayout,QLabel,QLineEdit,QPushButton,QGroupBox,QComboBox,QTableWidget,QTableWidgetItem,QHeaderView,QMessageBox,QFileDialog,QTabWidget,QDialog,QCheckBox,QSpinBox,QDoubleSpinBox,QDialogButtonBox,QFormLayout,QLabel as QLabel2,QColorDialog,QScrollArea,QFrame)
from analytics.filters import since_for
from export.pdf_export import make_report
from tiktok.live_client import TikTokLiveAdapter
from ui.overlay import ChatOverlay, GiftOverlay, RecentGiftOverlay, LikeOverlay, FollowOverlay
from ui.auth_window import AccountDialog
from settings import Settings
from sound import play_event_sound
from ai_reader import ChatReader
from web_overlay import BrowserOverlayServer
from gift_catalog import GiftCatalog
from live_data import record_dict, normalize_live_record, merge_chat_records, display_user
from browser_data import build_browser_snapshot
from cloud_config import EULER_HOME_URL, EULER_QUICKSTART_URL, EULER_REGISTER_URL

HQ_AVATAR_TARGET = 1080

class Bus(QObject):
    event=Signal(dict); status=Signal(str); profile=Signal(dict); avatar_ready=Signal(str,str)

class SettingsDialog(QDialog):
    """Compact, tabbed settings window.

    The old dialog used one very tall QFormLayout. On 768p/900p screens the
    lower controls and Save button could fall outside the visible area. Each
    category now has its own scrollable tab while Save/Cancel remain fixed at
    the bottom of the dialog.
    """
    def __init__(self,settings,parent=None):
        super().__init__(parent)
        self.settings=settings
        self.setWindowTitle('Ayarlar')
        self.resize(790,640)
        self.setMinimumSize(700,560)

        root=QVBoxLayout(self)
        root.setContentsMargins(12,12,12,12)
        root.setSpacing(10)
        self.settings_tabs=QTabWidget()
        root.addWidget(self.settings_tabs,1)

        # -------- Bağlantı --------
        page, f=self._form_tab('🔑 Bağlantı')
        key_group=QGroupBox('Euler / LIVE bağlantısı')
        kf=QFormLayout(key_group); kf.setSpacing(10)
        self.key=QLineEdit(settings.get('euler_api_key',''))
        self.key.setEchoMode(QLineEdit.Password)
        kf.addRow('Euler API Key',self.key)
        self.showkey=QCheckBox('Anahtarı göster')
        self.showkey.toggled.connect(lambda x:self.key.setEchoMode(QLineEdit.Normal if x else QLineEdit.Password))
        kf.addRow('',self.showkey)
        key_note=QLabel('Euler API anahtarı yalnızca bu cihazda saklanır ve bulut ayarlarına gönderilmez. Ortak bir anahtarı EXE içine gömmek güvenli olmadığı için her kullanıcı kendi anahtarını kullanır.')
        key_note.setWordWrap(True); key_note.setStyleSheet('color:#9aa4b2')
        kf.addRow('',key_note)
        euler_links=QHBoxLayout(); euler_links.setSpacing(8)
        euler_register=QPushButton('🌐 Euler hesabı aç')
        euler_register.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(EULER_REGISTER_URL)))
        euler_guide=QPushButton('🔑 API Key nasıl alınır?')
        euler_guide.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(EULER_QUICKSTART_URL)))
        euler_home=QPushButton('↗ EulerStream')
        euler_home.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(EULER_HOME_URL)))
        euler_links.addWidget(euler_register); euler_links.addWidget(euler_guide); euler_links.addWidget(euler_home)
        kf.addRow('Euler bağlantıları',euler_links)
        f.addRow(key_group)
        f.setRowWrapPolicy(QFormLayout.WrapLongRows)

        # -------- Sesler --------
        page, f=self._form_tab('🔊 Sesler')
        general=QGroupBox('Genel')
        gf=QFormLayout(general)
        self.sound=QCheckBox('Event ses sistemi aktif')
        self.sound.setChecked(settings.get('sound_enabled',True))
        gf.addRow('',self.sound)
        f.addRow(general)

        follow_box=QGroupBox('👥 Takip')
        ff=QFormLayout(follow_box); ff.setSpacing(8)
        self.sf=QCheckBox('Takip geldiğinde sesi çal'); self.sf.setChecked(settings.get('sound_follow',True)); ff.addRow('',self.sf)
        self.follow_sound=self._sound_picker(ff,'Ses dosyası',settings.get('sound_file_follow',''))
        self.follow_duration=self._duration_picker(ff,'Çalma süresi',settings.get('sound_duration_follow',0))
        f.addRow(follow_box)

        gift_box=QGroupBox('🎁 Hediye')
        ggf=QFormLayout(gift_box); ggf.setSpacing(8)
        self.sg=QCheckBox('Hediye geldiğinde sesi çal'); self.sg.setChecked(settings.get('sound_gift',True)); ggf.addRow('',self.sg)
        self.gift_sound=self._sound_picker(ggf,'Ses dosyası',settings.get('sound_file_gift',''))
        self.gift_duration=self._duration_picker(ggf,'Çalma süresi',settings.get('sound_duration_gift',0))
        f.addRow(gift_box)

        like_box=QGroupBox('❤️ Beğeni')
        lf=QFormLayout(like_box); lf.setSpacing(8)
        self.sl=QCheckBox('Beğeni geldiğinde sesi çal'); self.sl.setChecked(settings.get('sound_like',False)); lf.addRow('',self.sl)
        self.like_sound=self._sound_picker(lf,'Ses dosyası',settings.get('sound_file_like',''))
        self.like_duration=self._duration_picker(lf,'Çalma süresi',settings.get('sound_duration_like',0))
        f.addRow(like_box)

        chat_sound_box=QGroupBox('💬 Chat')
        cf=QFormLayout(chat_sound_box); cf.setSpacing(8)
        self.sc=QCheckBox('Chat geldiğinde sesi çal'); self.sc.setChecked(settings.get('sound_chat',False)); cf.addRow('',self.sc)
        self.chat_sound=self._sound_picker(cf,'Ses dosyası',settings.get('sound_file_chat',''))
        self.chat_duration=self._duration_picker(cf,'Çalma süresi',settings.get('sound_duration_chat',0))
        f.addRow(chat_sound_box)

        # -------- Chat okuma --------
        page, f=self._form_tab('🗣 Chat Okuma')
        tts_box=QGroupBox('Sesli okuma')
        tf=QFormLayout(tts_box); tf.setSpacing(9)
        self.ai=QCheckBox('Chat okuma botu aktif'); self.ai.setChecked(settings.get('ai_enabled',False)); tf.addRow('',self.ai)
        self.auto=QCheckBox('Yeni mesajları otomatik seslendir'); self.auto.setChecked(settings.get('ai_auto_read',False)); tf.addRow('',self.auto)
        self.rate=QSpinBox(); self.rate.setRange(80,280); self.rate.setValue(int(settings.get('ai_voice_rate',170))); tf.addRow('Ses hızı',self.rate)
        self.emote=QCheckBox('Emote-only mesajları oku'); self.emote.setChecked(not settings.get('ai_ignore_emotes',False)); tf.addRow('',self.emote)

        self.lang=QComboBox()
        langs=[('Türkçe (Türkiye)','tr-TR'),('English (US)','en-US'),('Deutsch','de-DE'),('Français','fr-FR'),('Español','es-ES')]
        for label,code in langs:self.lang.addItem(label,code)
        idx=max(0,self.lang.findData(settings.get('ai_language','tr-TR'))); self.lang.setCurrentIndex(idx)
        tf.addRow('Ses dili',self.lang)

        self.voice=QComboBox()
        self.voice.addItem('Otomatik (seçilen dile göre)', '')
        try:
            import pyttsx3
            engine=pyttsx3.init()
            for v in engine.getProperty('voices') or []:
                name=str(getattr(v,'name','') or getattr(v,'id','') or 'Ses')
                vid=str(getattr(v,'id','') or '')
                langs_text=str(getattr(v,'languages','') or '')
                self.voice.addItem(f'{name} • {langs_text}',vid)
            engine.stop()
        except Exception:
            pass
        edge_voices=[
            ('Türkçe Neural • Emel','edge:tr-TR-EmelNeural'),
            ('Türkçe Neural • Ahmet','edge:tr-TR-AhmetNeural'),
            ('English Neural • Jenny','edge:en-US-JennyNeural'),
            ('Deutsch Neural • Katja','edge:de-DE-KatjaNeural'),
        ]
        for label,vid in edge_voices:self.voice.addItem(label,vid)
        vi=self.voice.findData(settings.get('ai_voice_id',''))
        self.voice.setCurrentIndex(vi if vi>=0 else 0)
        tf.addRow('Ses motoru / ses',self.voice)
        self.read_names=self._check(tf,'Yorumcunun adını oku',settings.get('read_names',True))
        f.addRow(tts_box)

        filter_box=QGroupBox('Okuma filtreleri')
        filt=QFormLayout(filter_box); filt.setSpacing(9)
        self.skip_emojis=self._check(filt,'Emojileri seslendirme',settings.get('ai_skip_emojis',True))
        self.skip_spam=self._check(filt,'Spam mesajları okuma',settings.get('ai_skip_spam',True))
        self.skip_random=self._check(filt,'Random / klavye karışıklığı mesajlarını okuma',settings.get('ai_skip_random',True))
        self.skip_filtered=self._check(filt,'Filtreli sözcük içeren mesajları okuma',settings.get('ai_skip_filtered_words',True))
        self.filtered_words=QLineEdit(str(settings.get('ai_filtered_words','') or ''))
        self.filtered_words.setPlaceholderText('örn: küfür1, reklam, discord.gg, kelime')
        filt.addRow('Filtreli sözcükler',self.filtered_words)
        filter_note=QLabel('Filtreler birbirinden bağımsızdır. Filtreli sözcükleri virgül, noktalı virgül veya yeni satırla ayırabilirsin.')
        filter_note.setWordWrap(True); filter_note.setStyleSheet('color:#9aa4b2')
        filt.addRow('',filter_note)
        f.addRow(filter_box)

        roles_box=QGroupBox('Okunacak kullanıcı grupları')
        roles=QGridLayout(roles_box)
        self.read_all=QCheckBox('Tüm kullanıcılar'); self.read_all.setChecked(settings.get('read_all',True))
        self.read_followers=QCheckBox('Takipçiler'); self.read_followers.setChecked(settings.get('read_followers',True))
        self.read_gifters=QCheckBox('Hediye atanlar'); self.read_gifters.setChecked(settings.get('read_gifters',True))
        self.read_publisher=QCheckBox('Yayıncı'); self.read_publisher.setChecked(settings.get('read_publisher',True))
        self.read_mods=QCheckBox('Moderatörler'); self.read_mods.setChecked(settings.get('read_moderators',True))
        self.read_subs=QCheckBox('Aboneler'); self.read_subs.setChecked(settings.get('read_subscribers',True))
        self.read_normal=QCheckBox('Normal kullanıcılar'); self.read_normal.setChecked(settings.get('read_normal',True))
        checks=[self.read_all,self.read_followers,self.read_gifters,self.read_publisher,self.read_mods,self.read_subs,self.read_normal]
        for i,ch in enumerate(checks): roles.addWidget(ch,i//2,i%2)
        f.addRow(roles_box)
        self.note=QLabel('Türkçe sesler Windows konuşma seslerinde kuruluysa otomatik görünür. Neural sesler internet bağlantısı kullanabilir.')
        self.note.setWordWrap(True); self.note.setStyleSheet('color:#9aa4b2')
        f.addRow('',self.note)

        # -------- Chat / Widget --------
        page, f=self._form_tab('💬 Chat Widget')
        chat_res_box=QGroupBox('OBS / Browser Source çözünürlüğü')
        crf=QFormLayout(chat_res_box); crf.setSpacing(9)
        self.chat_resolution=QComboBox()
        for label,value in [
            ('Telefon Dikey • 360 x 640','phone_360x640'),
            ('Telefon Dikey • 480 x 800','phone_480x800'),
            ('Telefon Dikey • 600 x 1000','phone_600x1000'),
            ('Yatay Küçük • 800 x 600','landscape_800x600'),
            ('Yatay HD • 1280 x 720','hd_1280x720'),
            ('Özel','custom'),
        ]:
            self.chat_resolution.addItem(label,value)
        ri=self.chat_resolution.findData(settings.get('chat_widget_preset','phone_480x800'))
        self.chat_resolution.setCurrentIndex(ri if ri>=0 else 1)
        crf.addRow('Hazır çözünürlük',self.chat_resolution)
        self.chat_width=QSpinBox(); self.chat_width.setRange(240,3840); self.chat_width.setSuffix(' px'); self.chat_width.setValue(int(settings.get('chat_widget_width',480) or 480))
        self.chat_height=QSpinBox(); self.chat_height.setRange(240,3840); self.chat_height.setSuffix(' px'); self.chat_height.setValue(int(settings.get('chat_widget_height',800) or 800))
        crf.addRow('Genişlik',self.chat_width)
        crf.addRow('Yükseklik',self.chat_height)
        res_note=QLabel('Bu değerler OBS Browser Source için önerilen genişlik / yükseklik ayarıdır. Chat winget görünümünü hızlıca ayarlamak için kullanabilirsin.')
        res_note.setWordWrap(True); res_note.setStyleSheet('color:#9aa4b2')
        crf.addRow('',res_note)
        def _apply_chat_preset(index=None):
            preset=self.chat_resolution.currentData()
            mapping={'phone_360x640':(360,640),'phone_480x800':(480,800),'phone_600x1000':(600,1000),'landscape_800x600':(800,600),'hd_1280x720':(1280,720)}
            if preset in mapping:
                w,h=mapping[preset]
                self.chat_width.setValue(w); self.chat_height.setValue(h)
        self.chat_resolution.currentIndexChanged.connect(_apply_chat_preset)
        f.addRow(chat_res_box)

        chat_layout=QGroupBox('Görünüm')
        ctf=QFormLayout(chat_layout); ctf.setSpacing(9)
        self.chat_align=QComboBox()
        for label,value in [('Sola dayalı','left'),('Ortala','center'),('Sağa dayalı','right')]: self.chat_align.addItem(label,value)
        ci=self.chat_align.findData(settings.get('chat_align','left')); self.chat_align.setCurrentIndex(ci if ci>=0 else 0)
        ctf.addRow('Hizalama',self.chat_align)
        self.chat_show_avatar=self._check(ctf,'Profil fotoğraflarını göster',settings.get('chat_show_avatar',True))
        self.chat_show_title=self._check(ctf,'Widget başlığını göster',settings.get('chat_show_title',True))
        self.chat_avatar_size=QSpinBox(); self.chat_avatar_size.setRange(20,80); self.chat_avatar_size.setSuffix(' px'); self.chat_avatar_size.setValue(int(settings.get('chat_avatar_size',34) or 34)); ctf.addRow('Avatar boyutu',self.chat_avatar_size)
        self.chat_row_gap=QSpinBox(); self.chat_row_gap.setRange(0,24); self.chat_row_gap.setSuffix(' px'); self.chat_row_gap.setValue(int(settings.get('chat_row_gap',8) if settings.get('chat_row_gap',8) is not None else 8)); ctf.addRow('Satır boşluğu',self.chat_row_gap)
        self.chat_font_size=QSpinBox(); self.chat_font_size.setRange(12,42); self.chat_font_size.setSuffix(' px'); self.chat_font_size.setValue(int(settings.get('chat_font_size',18) or 18)); ctf.addRow('Mesaj yazı boyutu',self.chat_font_size)
        self.chat_title_size=QSpinBox(); self.chat_title_size.setRange(14,44); self.chat_title_size.setSuffix(' px'); self.chat_title_size.setValue(int(settings.get('chat_title_size',20) or 20)); ctf.addRow('Başlık yazı boyutu',self.chat_title_size)
        self.chat_bg_alpha=QSpinBox(); self.chat_bg_alpha.setRange(0,100); self.chat_bg_alpha.setSuffix(' %'); self.chat_bg_alpha.setValue(int(settings.get('chat_bg_alpha',48) if settings.get('chat_bg_alpha',48) is not None else 48)); ctf.addRow('Siyah arka plan',self.chat_bg_alpha)
        f.addRow(chat_layout)

        chat_effect=QGroupBox('Renkler ve efektler')
        cef=QFormLayout(chat_effect); cef.setSpacing(9)
        self.chat_text_rgb=self._rgb_picker(cef,'Mesaj rengi (RGB)',settings.get('chat_text_color','#ffffff'))
        self.chat_rgb=self._check(cef,'RGB / gökkuşağı yazı animasyonu',settings.get('chat_rgb_text',False))
        self.chat_wave=self._check(cef,'Wave yazı efekti',settings.get('chat_wave_text',False))
        self.chat_glow=self._check(cef,'Glow efekti',settings.get('chat_glow_text',False))
        f.addRow(chat_effect)

        # -------- Beğeni / Widget --------
        page, f=self._form_tab('❤️ Beğeni Widget')
        layout_box=QGroupBox('Yerleşim')
        wf=QFormLayout(layout_box); wf.setSpacing(9)
        self.like_align=QComboBox()
        for label,value in [('Sola dayalı','left'),('Ortala','center'),('Sağa dayalı','right')]: self.like_align.addItem(label,value)
        ai=self.like_align.findData(settings.get('like_align','left')); self.like_align.setCurrentIndex(ai if ai>=0 else 0)
        wf.addRow('Hizalama',self.like_align)
        self.like_show_avatar=self._check(wf,'Profil fotoğraflarını göster',settings.get('like_show_avatar',True))
        self.like_show_title=self._check(wf,'Widget başlığını göster',settings.get('like_show_title',True))
        self.like_avatar_size=QSpinBox(); self.like_avatar_size.setRange(20,80); self.like_avatar_size.setSuffix(' px'); self.like_avatar_size.setValue(int(settings.get('like_avatar_size',34) or 34)); wf.addRow('Avatar boyutu',self.like_avatar_size)
        self.like_row_gap=QSpinBox(); self.like_row_gap.setRange(0,24); self.like_row_gap.setSuffix(' px'); self.like_row_gap.setValue(int(settings.get('like_row_gap',6) if settings.get('like_row_gap',6) is not None else 6)); wf.addRow('Satır boşluğu',self.like_row_gap)
        self.like_bg_alpha=QSpinBox(); self.like_bg_alpha.setRange(0,100); self.like_bg_alpha.setSuffix(' %'); self.like_bg_alpha.setValue(int(settings.get('like_bg_alpha',48) if settings.get('like_bg_alpha',48) is not None else 48)); wf.addRow('Siyah arka plan',self.like_bg_alpha)
        f.addRow(layout_box)

        color_box=QGroupBox('Renkler ve efektler')
        ef=QFormLayout(color_box); ef.setSpacing(9)
        self.like_text_rgb=self._rgb_picker(ef,'Kullanıcı / sıra rengi (RGB)',settings.get('like_text_color','#ff5b7f'))
        self.like_count_rgb=self._rgb_picker(ef,'Beğeni sayısı rengi (RGB)',settings.get('like_count_color','#ffffff'))
        self.like_heart_rgb=self._rgb_picker(ef,'Kalp rengi (RGB)',settings.get('like_heart_color','#ff2f67'))
        self.like_rgb=self._check(ef,'RGB / gökkuşağı yazı animasyonu',settings.get('like_rgb_text',False))
        self.like_wave=self._check(ef,'Wave yazı efekti',settings.get('like_wave_text',False))
        self.like_glow=self._check(ef,'Glow efekti',settings.get('like_glow_text',True))
        f.addRow(color_box)


        # -------- Hediye / Widget --------
        page, f=self._form_tab('🎁 Hediye Widget')
        gift_layout=QGroupBox('Yerleşim')
        gwf=QFormLayout(gift_layout); gwf.setSpacing(9)
        self.gift_align=QComboBox()
        for label,value in [('Sola dayalı','left'),('Ortala','center'),('Sağa dayalı','right')]: self.gift_align.addItem(label,value)
        gi=self.gift_align.findData(settings.get('gift_align','left')); self.gift_align.setCurrentIndex(gi if gi>=0 else 0)
        gwf.addRow('Hizalama',self.gift_align)
        self.gift_show_avatar=self._check(gwf,'Profil fotoğraflarını göster',settings.get('gift_show_avatar',True))
        self.gift_show_title=self._check(gwf,'Widget başlığını göster',settings.get('gift_show_title',True))
        self.gift_avatar_size=QSpinBox(); self.gift_avatar_size.setRange(20,80); self.gift_avatar_size.setSuffix(' px'); self.gift_avatar_size.setValue(int(settings.get('gift_avatar_size',34) or 34)); gwf.addRow('Avatar boyutu',self.gift_avatar_size)
        self.gift_row_gap=QSpinBox(); self.gift_row_gap.setRange(0,24); self.gift_row_gap.setSuffix(' px'); self.gift_row_gap.setValue(int(settings.get('gift_row_gap',6) if settings.get('gift_row_gap',6) is not None else 6)); gwf.addRow('Satır boşluğu',self.gift_row_gap)
        self.gift_bg_alpha=QSpinBox(); self.gift_bg_alpha.setRange(0,100); self.gift_bg_alpha.setSuffix(' %'); self.gift_bg_alpha.setValue(int(settings.get('gift_bg_alpha',48) if settings.get('gift_bg_alpha',48) is not None else 48)); gwf.addRow('Siyah arka plan',self.gift_bg_alpha)
        f.addRow(gift_layout)
        gift_effect=QGroupBox('Renkler ve efektler')
        gef=QFormLayout(gift_effect); gef.setSpacing(9)
        self.gift_text_rgb=self._rgb_picker(gef,'Yazı rengi (RGB)',settings.get('gift_text_color','#ffd166'))
        self.gift_rgb=self._check(gef,'RGB / gökkuşağı yazı animasyonu',settings.get('gift_rgb_text',False))
        self.gift_wave=self._check(gef,'Wave yazı efekti',settings.get('gift_wave_text',False))
        self.gift_glow=self._check(gef,'Glow efekti',settings.get('gift_glow_text',True))
        f.addRow(gift_effect)

        # -------- Takip / Widget --------
        page, f=self._form_tab('👥 Takip Widget')
        follow_layout=QGroupBox('Yerleşim')
        fwf=QFormLayout(follow_layout); fwf.setSpacing(9)
        self.follow_align=QComboBox()
        for label,value in [('Sola dayalı','left'),('Ortala','center'),('Sağa dayalı','right')]: self.follow_align.addItem(label,value)
        fi=self.follow_align.findData(settings.get('follow_align','left')); self.follow_align.setCurrentIndex(fi if fi>=0 else 0)
        fwf.addRow('Hizalama',self.follow_align)
        self.follow_show_avatar=self._check(fwf,'Profil fotoğraflarını göster',settings.get('follow_show_avatar',True))
        self.follow_show_title=self._check(fwf,'Widget başlığını göster',settings.get('follow_show_title',True))
        self.follow_avatar_size=QSpinBox(); self.follow_avatar_size.setRange(20,80); self.follow_avatar_size.setSuffix(' px'); self.follow_avatar_size.setValue(int(settings.get('follow_avatar_size',34) or 34)); fwf.addRow('Avatar boyutu',self.follow_avatar_size)
        self.follow_row_gap=QSpinBox(); self.follow_row_gap.setRange(0,24); self.follow_row_gap.setSuffix(' px'); self.follow_row_gap.setValue(int(settings.get('follow_row_gap',6) if settings.get('follow_row_gap',6) is not None else 6)); fwf.addRow('Satır boşluğu',self.follow_row_gap)
        self.follow_bg_alpha=QSpinBox(); self.follow_bg_alpha.setRange(0,100); self.follow_bg_alpha.setSuffix(' %'); self.follow_bg_alpha.setValue(int(settings.get('follow_bg_alpha',48) if settings.get('follow_bg_alpha',48) is not None else 48)); fwf.addRow('Siyah arka plan',self.follow_bg_alpha)
        f.addRow(follow_layout)
        follow_effect=QGroupBox('Renkler ve efektler')
        fef=QFormLayout(follow_effect); fef.setSpacing(9)
        self.follow_text_rgb=self._rgb_picker(fef,'Yazı rengi (RGB)',settings.get('follow_text_color','#ffffff'))
        self.follow_rgb=self._check(fef,'RGB / gökkuşağı yazı animasyonu',settings.get('follow_rgb_text',False))
        self.follow_wave=self._check(fef,'Wave yazı efekti',settings.get('follow_wave_text',False))
        self.follow_glow=self._check(fef,'Glow efekti',settings.get('follow_glow_text',False))
        f.addRow(follow_effect)

        # Save / Cancel never scrolls out of view.
        buttons=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText('Kaydet')
        buttons.button(QDialogButtonBox.Cancel).setText('İptal')
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _form_tab(self,title):
        scroll=QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        body=QWidget()
        form=QFormLayout(body)
        form.setContentsMargins(12,12,12,12)
        form.setSpacing(10)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        form.setLabelAlignment(Qt.AlignLeft|Qt.AlignVCenter)
        scroll.setWidget(body)
        self.settings_tabs.addTab(scroll,title)
        return body,form

    def _check(self,form,label,value):
        x=QCheckBox(label); x.setChecked(bool(value)); form.addRow('',x); return x

    def _sound_picker(self,form,label,current):
        row=QHBoxLayout(); edit=QLineEdit(current or ''); edit.setReadOnly(True); btn=QPushButton('Dosya seç')
        def choose():
            path,_=QFileDialog.getOpenFileName(self,'Event sesi seç',edit.text() or '', 'Ses dosyaları (*.mp3 *.wav *.ogg *.flac *.m4a);;Tüm dosyalar (*.*)')
            if path: edit.setText(path)
        btn.clicked.connect(choose); row.addWidget(edit,1); row.addWidget(btn); form.addRow(label,row); return edit

    def _duration_picker(self,form,label,current):
        box=QDoubleSpinBox(); box.setRange(0.0,600.0); box.setSingleStep(0.5); box.setDecimals(1); box.setSuffix(' sn'); box.setSpecialValueText('Tamamı'); box.setValue(float(current or 0)); form.addRow(label,box); return box

    def _rgb_picker(self,form,label,current):
        color=QColor(str(current or '#ffffff'))
        if not color.isValid(): color=QColor('#ffffff')
        row=QHBoxLayout(); boxes=[]
        for value in (color.red(),color.green(),color.blue()):
            b=QSpinBox(); b.setRange(0,255); b.setValue(value); b.setFixedWidth(78); boxes.append(b); row.addWidget(b)
        pick=QPushButton('🎨 Seç')
        def choose():
            c=QColorDialog.getColor(QColor(boxes[0].value(),boxes[1].value(),boxes[2].value()),self,'Renk seç')
            if c.isValid():
                boxes[0].setValue(c.red()); boxes[1].setValue(c.green()); boxes[2].setValue(c.blue())
        pick.clicked.connect(choose); row.addWidget(pick); form.addRow(label,row); return boxes

    @staticmethod
    def _rgb_hex(boxes):
        return '#%02x%02x%02x' % tuple(int(b.value()) for b in boxes)

    def accept(self):
        self.settings.data.update({
            'euler_api_key':self.key.text().strip(),
            'sound_enabled':self.sound.isChecked(),
            'sound_follow':self.sf.isChecked(),'sound_gift':self.sg.isChecked(),
            'sound_like':self.sl.isChecked(),'sound_chat':self.sc.isChecked(),
            'sound_file_follow':self.follow_sound.text(),'sound_file_gift':self.gift_sound.text(),
            'sound_file_like':self.like_sound.text(),'sound_file_chat':self.chat_sound.text(),
            'sound_duration_follow':self.follow_duration.value(),'sound_duration_gift':self.gift_duration.value(),
            'sound_duration_like':self.like_duration.value(),'sound_duration_chat':self.chat_duration.value(),
            'ai_enabled':self.ai.isChecked(),'ai_auto_read':self.auto.isChecked(),
            'ai_voice_rate':self.rate.value(),'ai_ignore_emotes':not self.emote.isChecked(),
            'ai_skip_emojis':self.skip_emojis.isChecked(),'ai_skip_spam':self.skip_spam.isChecked(),
            'ai_skip_random':self.skip_random.isChecked(),'ai_skip_filtered_words':self.skip_filtered.isChecked(),
            'ai_filtered_words':self.filtered_words.text().strip(),
            'ai_language':self.lang.currentData(),'ai_voice_id':self.voice.currentData() or '',
            'read_all':self.read_all.isChecked(),'read_names':self.read_names.isChecked(),'read_followers':self.read_followers.isChecked(),
            'read_gifters':self.read_gifters.isChecked(),'read_publisher':self.read_publisher.isChecked(),
            'read_moderators':self.read_mods.isChecked(),'read_subscribers':self.read_subs.isChecked(),
            'read_normal':self.read_normal.isChecked(),
            'chat_widget_preset':self.chat_resolution.currentData() or 'phone_480x800',
            'chat_widget_width':self.chat_width.value(),'chat_widget_height':self.chat_height.value(),
            'chat_align':self.chat_align.currentData() or 'left','chat_text_color':self._rgb_hex(self.chat_text_rgb),
            'chat_rgb_text':self.chat_rgb.isChecked(),'chat_wave_text':self.chat_wave.isChecked(),'chat_glow_text':self.chat_glow.isChecked(),
            'chat_show_avatar':self.chat_show_avatar.isChecked(),'chat_show_title':self.chat_show_title.isChecked(),
            'chat_avatar_size':self.chat_avatar_size.value(),'chat_row_gap':self.chat_row_gap.value(),'chat_bg_alpha':self.chat_bg_alpha.value(),
            'chat_font_size':self.chat_font_size.value(),'chat_title_size':self.chat_title_size.value(),
            'like_align':self.like_align.currentData() or 'left',
            'like_text_color':self._rgb_hex(self.like_text_rgb),'like_count_color':self._rgb_hex(self.like_count_rgb),'like_heart_color':self._rgb_hex(self.like_heart_rgb),
            'like_rgb_text':self.like_rgb.isChecked(),'like_wave_text':self.like_wave.isChecked(),'like_glow_text':self.like_glow.isChecked(),
            'like_show_avatar':self.like_show_avatar.isChecked(),'like_show_title':self.like_show_title.isChecked(),
            'like_avatar_size':self.like_avatar_size.value(),'like_row_gap':self.like_row_gap.value(),'like_bg_alpha':self.like_bg_alpha.value(),
            'gift_align':self.gift_align.currentData() or 'left','gift_text_color':self._rgb_hex(self.gift_text_rgb),
            'gift_rgb_text':self.gift_rgb.isChecked(),'gift_wave_text':self.gift_wave.isChecked(),'gift_glow_text':self.gift_glow.isChecked(),
            'gift_show_avatar':self.gift_show_avatar.isChecked(),'gift_show_title':self.gift_show_title.isChecked(),
            'gift_avatar_size':self.gift_avatar_size.value(),'gift_row_gap':self.gift_row_gap.value(),'gift_bg_alpha':self.gift_bg_alpha.value(),
            'follow_align':self.follow_align.currentData() or 'left','follow_text_color':self._rgb_hex(self.follow_text_rgb),
            'follow_rgb_text':self.follow_rgb.isChecked(),'follow_wave_text':self.follow_wave.isChecked(),'follow_glow_text':self.follow_glow.isChecked(),
            'follow_show_avatar':self.follow_show_avatar.isChecked(),'follow_show_title':self.follow_show_title.isChecked(),
            'follow_avatar_size':self.follow_avatar_size.value(),'follow_row_gap':self.follow_row_gap.value(),'follow_bg_alpha':self.follow_bg_alpha.value()
        })
        self.settings.save()
        super().accept()

class MainWindow(QMainWindow):
    def __init__(self,db,base,account=None,auth_store=None,data_dir=None,logout_callback=None):
        super().__init__()
        self.db=db
        self.base=Path(base)
        self.account=dict(account or {})
        self.auth_store=auth_store
        self.data_dir=Path(data_dir or (self.base/'data'))
        self.data_dir.mkdir(parents=True,exist_ok=True)
        self.logout_callback=logout_callback
        self._logout_requested=False
        self.settings=Settings(base,self.account.get('id'),cloud_store=self.auth_store)
        self.reader=ChatReader(self.settings)
        self.sid=None; self.adapter=None; self.profile={}; self.freeze_view=False; self.dirty=False; self.last_like_total=0
        self.avatar_dir=self.data_dir/'avatars'; self.avatar_dir.mkdir(parents=True,exist_ok=True)
        self.avatar_hq_dir=self.data_dir/'avatar_hq_cache'; self.avatar_hq_dir.mkdir(parents=True,exist_ok=True)
        self.avatar_paths={}; self.avatar_pending=set()
        self.stats={'viewers':0,'gifts':0,'likes':0,'follows':0,'chats':0,'joins':0,'max':0,'diamonds':0}
        self.live_connected=False; self.last_room_viewer_at=0.0
        self.gift_catalog=GiftCatalog(self.data_dir); self.gift_catalog.start()
        self.followers_set=set(); self.gifters_set=set(); self.moderators_set=set(); self.subscribers_set=set(); self._love_users=set(); self.chat_cache=[]
        self.broadcaster_username=str(self.account.get('publisher_username') or '').strip().lower()
        self.browser_test_until={}
        self.bus=Bus(); self.bus.event.connect(self.on_event); self.bus.status.connect(self.set_status); self.bus.profile.connect(self.on_profile); self.bus.avatar_ready.connect(self.on_avatar_ready)
        self.chat=ChatOverlay(); self.gift=GiftOverlay(); self.gift.apply_list_style(self.gift_style()); self.recent_gift=RecentGiftOverlay(); self.recent_gift.apply_list_style(self.gift_style()); self.like=LikeOverlay(); self.like.apply_like_style(self.like_style()); self.follow=FollowOverlay(); self.follow.apply_list_style(self.follow_style())
        self.browser=BrowserOverlayServer(self.browser_snapshot, port=int(self.settings.get('browser_port',8765) or 8765)); self.browser.start()
        self.setWindowTitle('RπM Studio')
        self.resize(1280,840)
        self.build()
        self.timer=QTimer(self); self.timer.timeout.connect(self.refresh); self.timer.start(700)
    def build(self):
        self.setStyleSheet('QWidget{background:#0d1320;color:#eef4fb;font-family:Segoe UI;font-size:13px} QWidget#appRoot{background:qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #0b1220, stop:1 #101827)} QGroupBox{background:#101827;border:1px solid rgba(123,152,196,0.18);border-radius:14px;margin-top:10px;padding:12px;font-weight:700} QGroupBox::title{subcontrol-origin:margin;left:12px;padding:0 6px;color:#dfeaff} QLineEdit,QComboBox,QSpinBox,QDoubleSpinBox{background:#0f1724;color:#f9fbff;border:1px solid rgba(134,163,206,0.22);border-radius:10px;padding:9px 11px;selection-background-color:#2f6fed} QLineEdit:focus,QComboBox:focus,QSpinBox:focus,QDoubleSpinBox:focus{border:1px solid #5ea7ff} QPushButton{background:#172437;color:white;border:1px solid rgba(255,255,255,0.07);border-radius:10px;padding:10px 14px;font-weight:700} QPushButton:hover{background:#1d2d45} QPushButton:pressed{background:#162131} QPushButton:checked{background:#214b7b;border-color:#66b3ff} QLabel{background:transparent} QTabWidget::pane{border:1px solid rgba(130,160,210,0.16);border-radius:14px;top:-1px;background:#0f1724} QTabBar::tab{background:#111a28;color:#d7dfeb;border:1px solid rgba(255,255,255,0.05);padding:9px 14px;border-top-left-radius:10px;border-top-right-radius:10px;margin-right:4px} QTabBar::tab:selected{background:#182439;color:#ffffff;border-color:rgba(94,167,255,0.40)} QTableWidget{background:#0f1724;alternate-background-color:#121d2d;gridline-color:#233145;border:1px solid rgba(255,255,255,0.05);border-radius:10px} QHeaderView::section{background:#17253a;color:#eff5ff;padding:8px;border:none;border-right:1px solid rgba(255,255,255,0.05)} QScrollBar:vertical{background:#0d1420;width:12px;margin:0;border-radius:6px} QScrollBar::handle:vertical{background:#34506e;min-height:24px;border-radius:6px} QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{height:0} QTableCornerButton::section{background:#17253a;border:none}')
        root=QWidget(); root.setObjectName('appRoot'); main=QVBoxLayout(root); main.setContentsMargins(16,16,16,16); main.setSpacing(12)

        # Header
        header_box=QGroupBox('🎛 RπM Studio')
        hb=QVBoxLayout(header_box)
        hb.setSpacing(10)
        top=QHBoxLayout(); top.setSpacing(10)
        brand=QLabel('RπM Studio')
        brand.setStyleSheet('font-size:24px;font-weight:900;color:#ffffff')
        top.addWidget(brand)
        self.user=QLineEdit(str(self.account.get('publisher_username') or ''))
        self.user.setPlaceholderText('TikTok yayıncı adı')
        self.user.setReadOnly(bool(self.account))
        self.user.setToolTip('Yayıncı adı hesabına bağlıdır. Değiştirmek için Hesap bölümünü kullan.')
        self.status_dot=QLabel('●'); self.status_text=QLabel('BAĞLI DEĞİL'); self.status_detail=QLabel('Hazır'); self.set_status('BAĞLI DEĞİL')
        self.connect_button=QPushButton('▶ LIVE Bağlan'); self.connect_button.clicked.connect(self.connect_live)
        top.addWidget(self.user,2); top.addWidget(self.status_dot); top.addWidget(self.status_text); top.addWidget(self.status_detail,2); top.addWidget(self.connect_button)
        hb.addLayout(top)

        quick=QHBoxLayout(); quick.setSpacing(8)
        demo=QPushButton('🧪 Demo'); demo.clicked.connect(self.demo)
        pdf=QPushButton('📄 PDF'); pdf.clicked.connect(self.pdf)
        settings=QPushButton('⚙ Ayarlar'); settings.clicked.connect(self.open_settings)
        account_text=(str(self.account.get('email') or 'Hesap').split('@')[0] or 'Hesap')
        self.account_button=QPushButton('👤 '+account_text)
        self.account_button.clicked.connect(self.open_account)
        self.freeze_button=QPushButton('🔓 Canlı Veri'); self.freeze_button.setCheckable(True); self.freeze_button.clicked.connect(self.toggle_freeze)
        for b in (demo,pdf,settings,self.account_button,self.freeze_button): quick.addWidget(b)
        quick.addStretch(1)
        hb.addLayout(quick)

        self.profile_label=QLabel('☁ Global hesap • Profil: @'+str(self.account.get('publisher_username') or '-')+' • '+str(self.account.get('email') or '-'))
        self.profile_label.setStyleSheet('color:#91a3bb;padding-left:2px')
        hb.addWidget(self.profile_label)
        main.addWidget(header_box)

        sections=QTabWidget(); self.main_sections=sections

        # Dashboard tab
        dash_page=QWidget(); dash_layout=QVBoxLayout(dash_page); dash_layout.setSpacing(12)
        metrics_box=QGroupBox('📊 Canlı Özet')
        grid=QGridLayout(metrics_box); grid.setHorizontalSpacing(12); grid.setVerticalSpacing(12); self.card={}
        metric_items=[('viewers','👁 Anlık İzleyici'),('max','📈 Maks. İzleyici'),('likes','❤️ Toplam Beğeni'),('gifts','🎁 Toplam Hediye'),('follows','👥 Takip'),('chats','💬 Chat')]
        for i,(k,t) in enumerate(metric_items):
            b=QGroupBox(t); l=QVBoxLayout(b); x=QLabel('0'); x.setAlignment(Qt.AlignCenter); x.setFont(QFont('Segoe UI',20,QFont.Bold)); l.addWidget(x); self.card[k]=x; grid.addWidget(b,i//3,i%3)
        dash_layout.addWidget(metrics_box)

        launch_box=QGroupBox('🚀 Hızlı Aç')
        acts=QGridLayout(launch_box); acts.setHorizontalSpacing(8); acts.setVerticalSpacing(8)
        quick_buttons=[('💬 Chat',self.show_chat),('🎁 Hediyeler',self.show_gift),('🎁 Son Hediyeler',self.show_recent_gift),('❤️ Beğeniler',self.show_like),('👥 Takipçiler',self.show_follow),('🪟 Tüm Pencereler',self.show_all)]
        for i,(txt,fn) in enumerate(quick_buttons):
            b=QPushButton(txt); b.clicked.connect(fn); acts.addWidget(b,i//3,i%3)
        dash_layout.addWidget(launch_box)

        recent_box=QGroupBox('🕒 Son Hareketler')
        recent_layout=QVBoxLayout(recent_box)
        self.table=QTableWidget(0,4); self.table.setHorizontalHeaderLabels(['Zaman','Kullanıcı','Tür','Detay']); self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        recent_layout.addWidget(self.table)
        dash_layout.addWidget(recent_box,1)
        sections.addTab(dash_page,'🏠 Kontrol Merkezi')

        # OBS / widget tab
        widget_page=QWidget(); widget_layout=QVBoxLayout(widget_page); widget_layout.setSpacing(10)
        self.browser_url_label=QLabel(f'OBS sunucusu: http://localhost:{self.browser.port}/chat')
        self.browser_url_label.setStyleSheet('color:#9aa4b2')
        widget_layout.addWidget(self.browser_url_label)
        obs_box=QGroupBox('🎥 OBS / Browser Source')
        obs_grid=QGridLayout(obs_box)
        baseurl=f'http://localhost:{self.browser.port}'
        chat_label=f"Chat ({int(self.settings.get('chat_widget_width',480) or 480)}x{int(self.settings.get('chat_widget_height',800) or 800)})"
        for rr,(label,path,mode) in enumerate([(chat_label,'/chat','chat'),('Hediyeler','/gifts','gifts'),('Son Hediyeler','/recent-gifts','recent-gifts'),('Beğeni','/likes','likes'),('Takip','/followers','followers'),('Katılanlar','/joins','joins'),('İzleyici','/viewers','viewers')]):
            url=baseurl+path
            obs_grid.addWidget(QLabel(label),rr,0)
            edit=QLineEdit(url); edit.setReadOnly(True); obs_grid.addWidget(edit,rr,1)
            cp=QPushButton('📋 Kopyala'); cp.clicked.connect(lambda _,x=edit: QApplication.clipboard().setText(x.text())); obs_grid.addWidget(cp,rr,2)
            op=QPushButton('🌐 Aç'); op.clicked.connect(lambda _,x=edit: QDesktopServices.openUrl(QUrl(x.text()))); obs_grid.addWidget(op,rr,3)
            test=QPushButton('🧪 Dene'); test.setToolTip('Bu Browser Source için 5 saniyelik örnek veri gösterir.'); test.clicked.connect(lambda _,m=mode:self.test_browser_source(m)); obs_grid.addWidget(test,rr,4)
        widget_layout.addWidget(obs_box)
        help_box=QGroupBox('ℹ Kullanım')
        hl=QVBoxLayout(help_box)
        tip=QLabel('OBS içinde Browser Source ekleyip yukarıdaki linklerden birini yapıştırabilirsin. Aç düğmesi linki tarayıcıda test eder, Dene düğmesi ise 5 saniyelik örnek veri gösterir.')
        tip.setWordWrap(True); tip.setStyleSheet('color:#9aa4b2')
        hl.addWidget(tip)
        widget_layout.addWidget(help_box)
        widget_layout.addStretch(1)
        sections.addTab(widget_page,'🎥 Widget / OBS')

        # Lists tab
        lists_page=QWidget(); lists_layout=QVBoxLayout(lists_page)
        tabs=QTabWidget(); self.tabs=tabs
        dash=QWidget(); dl=QVBoxLayout(dash); self.general_table=QTableWidget(0,4); self.general_table.setHorizontalHeaderLabels(['Zaman','Kullanıcı','Tür','Detay']); self.general_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch); dl.addWidget(self.general_table); tabs.addTab(dash,'📊 Genel')
        cp=QVBoxLayout(); page=QWidget(); page.setLayout(cp); self.chat_table=QTableWidget(0,3); self.chat_table.setHorizontalHeaderLabels(['Kullanıcı','Mesaj','Zaman']); self.chat_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch); cp.addWidget(self.chat_table); tabs.addTab(page,'💬 Chat')
        gp=QVBoxLayout(); page=QWidget(); page.setLayout(gp); self.gift_table=QTableWidget(0,5); self.gift_table.setHorizontalHeaderLabels(['Sıra','Kullanıcı','Hediye','Adet','Puan']); self.gift_table.cellClicked.connect(self.preview_table_image); self.gift_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch); gp.addWidget(self.gift_table); tabs.addTab(page,'🎁 Hediyeler')
        lp=QVBoxLayout(); page=QWidget(); page.setLayout(lp); self.like_table=QTableWidget(0,3); self.like_table.setHorizontalHeaderLabels(['Sıra','Kullanıcı','Beğeni']); self.like_table.cellClicked.connect(self.preview_table_image); self.like_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch); lp.addWidget(self.like_table); tabs.addTab(page,'❤️ Beğeniler')
        fp=QVBoxLayout(); page=QWidget(); page.setLayout(fp); bar=QHBoxLayout(); bar.addWidget(QLabel('Filtre')); self.filter=QComboBox(); self.filter.addItems(['Bugün','Dün','Bu ay','Bu yıl','Tüm zamanlar']); self.filter.currentIndexChanged.connect(self.force_refresh); bar.addWidget(self.filter); bar.addStretch(); fp.addLayout(bar); self.follow_table=QTableWidget(0,2); self.follow_table.setHorizontalHeaderLabels(['Zaman','Kullanıcı']); self.follow_table.cellClicked.connect(self.preview_table_image); self.follow_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch); fp.addWidget(self.follow_table); tabs.addTab(page,'👥 Takipçiler')
        jp=QVBoxLayout(); page=QWidget(); page.setLayout(jp); self.join_table=QTableWidget(0,2); self.join_table.setHorizontalHeaderLabels(['Zaman','Kullanıcı']); self.join_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch); jp.addWidget(self.join_table); tabs.addTab(page,'🚪 Katıldı')
        lists_layout.addWidget(tabs)
        sections.addTab(lists_page,'🗂 Veri Listeleri')

        main.addWidget(sections,1)
        self.setCentralWidget(root)
    def _set_row(self, table, row, values):
        if row >= table.rowCount():
            table.insertRow(row)
        for col,val in enumerate(values):
            table.setItem(row,col,QTableWidgetItem(str(val)))

    def _sync_general_views(self, rows):
        targets=[]
        if hasattr(self,'table') and self.table is not None: targets.append(self.table)
        if hasattr(self,'general_table') and self.general_table is not None: targets.append(self.general_table)
        for t in targets:
            t.setRowCount(0)
            for r,vals in enumerate(rows):
                self._set_row(t,r,vals)

    def open_account(self):
        if not self.auth_store or not self.account:
            QMessageBox.information(self,'Hesap','Bu oturumda hesap yöneticisi kullanılamıyor.')
            return
        dlg=AccountDialog(self.auth_store,self.account,self)
        dlg.accountUpdated.connect(self._account_updated)
        dlg.logoutRequested.connect(self._request_logout)
        dlg.exec()

    def _account_updated(self,account):
        self.account=dict(account or self.account)
        publisher=str(self.account.get('publisher_username') or '').strip()
        if not self.live_connected:
            self.broadcaster_username=publisher.lower()
        else:
            self.status_detail.setText('Yayıncı adı güncellendi • sonraki LIVE bağlantısında uygulanacak')
        self.user.setText(publisher)
        account_text=(str(self.account.get('email') or 'Hesap').split('@')[0] or 'Hesap')
        self.account_button.setText('👤 '+account_text)
        self.profile_label.setText('☁ Global hesap • Profil: @'+publisher+' • '+str(self.account.get('email') or '-'))

    def _request_logout(self):
        self._logout_requested=True
        try:
            if self.auth_store:
                self.auth_store.clear_local_session(self.account.get('id'))
        except Exception:
            pass
        self.close()

    def set_status(self,text):
        text=str(text or '')
        u=text.upper(); c='#e53935'; lab='BAĞLI DEĞİL'
        if 'BAĞLANIYOR' in u:
            c='#f4c20d'; lab='BAĞLANIYOR'
        elif ('BAĞLANDI' in u or 'BAĞLI •' in u) and 'HATA' not in u:
            c='#20c967'; lab='BAĞLANDI'
        elif 'HATA' in u or 'BAŞARISIZ' in u:
            c='#e53935'; lab='BAĞLANTI HATASI'
        detail=text
        for prefix in ('BAĞLANTI HATASI • ', 'BAĞLANIYOR • ', 'BAĞLANDI • ', 'BAĞLI DEĞİL • '):
            if detail.upper().startswith(prefix.upper()):
                detail=detail[len(prefix):]
                break
        self.status_dot.setStyleSheet(f'color:{c};font-size:20px')
        self.status_text.setText(lab)
        self.status_detail.setText(detail or text)
    def open_settings(self):
        if SettingsDialog(self.settings,self).exec():
            self.reader.update_settings(self.settings)
            self.like.apply_like_style(self.like_style())
            self.gift.apply_list_style(self.gift_style())
            self.recent_gift.apply_list_style(self.gift_style())
            self.follow.apply_list_style(self.follow_style())
            self.dirty = True
            QTimer.singleShot(0, self.refresh)
            if self.live_connected:
                self.set_status('BAĞLI • Ayarlar kaydedildi • LIVE bağlantısı korunuyor')
            else:
                self.set_status('Ayarlar kaydedildi • LIVE bağlantısı korunuyor')
    def _set_connect_button(self, text, slot):
        try:
            self.connect_button.clicked.disconnect()
        except (TypeError, RuntimeError):
            pass
        self.connect_button.setText(text)
        self.connect_button.clicked.connect(slot)

    def connect_live(self):
        u=self.user.text().strip().lstrip('@'); key=self.settings.get('euler_api_key','').strip()
        if not u or not key: QMessageBox.warning(self,'Eksik','TikTok kullanıcı adını girin ve ⚙ Ayarlar > Euler API Key bölümünden anahtarı kaydedin.'); return
        if self.adapter:self.stop_live()
        self.stats={k:0 for k in self.stats}; self.last_like_total=0; self.live_connected=False; self.last_room_viewer_at=0.0; self.followers_set=set(); self.gifters_set=set(); self.moderators_set=set(); self.subscribers_set=set(); self._love_users=set(); self.chat_cache=[]; self.broadcaster_username=u.lower(); self.chat_cache=[]; self.sid=self.db.start_session(u); self.set_status('BAĞLANIYOR • Euler LIVE kontrolü başlatılıyor...'); self._set_connect_button('⏹ Durdur', self.stop_live)
        threading.Thread(target=self.fetch_profile,args=(u,key),daemon=True).start(); self.adapter=TikTokLiveAdapter(u,key,self.bus.event.emit,self.bus.status.emit); self.adapter.start()
    def fetch_profile(self,u,key):
        try:
            r=requests.get(f'https://api.eulerstream.com/tiktok/users/{u}/basic',headers={'X-Api-Key':key},timeout=8); r.raise_for_status(); d=r.json(); self.bus.profile.emit(d.get('user',d.get('data',{})) or {})
        except Exception as e:self.bus.profile.emit({'_error':str(e),'unique_id':u})
    def on_profile(self,p):
        if '_error' in p:self.profile_label.setText('Profil: alınamadı • '+p['_error']); return
        self.profile=p; self.profile_label.setText(f"Profil: {p.get('nickname') or self.user.text().lstrip('@')} • @{p.get('unique_id') or self.user.text().lstrip('@')} • Bölge: {p.get('region') or p.get('region_code') or '-'}")
    def _avatar_path(self,u,url):
        if not u or not url:return ''
        k=hashlib.sha1(url.encode()).hexdigest(); path=self.avatar_dir/f'{k}.img'
        if path.exists():self.avatar_paths[u.lower()]=str(path);return str(path)
        if u.lower() in self.avatar_pending:return ''
        self.avatar_pending.add(u.lower())
        def worker():
            try:
                r=requests.get(url,headers={'User-Agent':'Mozilla/5.0'},timeout=6); r.raise_for_status(); path.write_bytes(r.content); self.bus.avatar_ready.emit(u,str(path))
            except Exception:self.bus.avatar_ready.emit(u,'')
        threading.Thread(target=worker,daemon=True).start(); return ''
    def avatar_for(self,u,url=''):
        return self.avatar_paths.get((u or '').lower(),'') or self._avatar_path(u,url)
    def on_avatar_ready(self,u,path):
        self.avatar_pending.discard(u.lower());
        if path:self.avatar_paths[u.lower()]=path
        self.dirty=True
    def stop_live(self):
        if self.adapter:self.adapter.stop()
        if self.sid:self.db.end_session(self.sid)
        self.adapter=None; self.set_status('BAĞLI DEĞİL'); self._set_connect_button('LIVE Bağlan', self.connect_live)
    def classify(self,e):
        u=(e.get('username') or '').strip().lower(); pub=self.broadcaster_username or self.user.text().strip().lstrip('@').lower(); role=(e.get('role') or '').lower(); msg=(e.get('message') or '')
        if pub and u==pub:return 'publisher'
        if role=='moderator' or u in self.moderators_set:return 'moderator'
        if role=='subscriber' or u in self.subscribers_set:return 'subscriber'
        if u in self._love_users:return 'love'
        # Only classify as Beni Sev after an explicit phrase, never just because
        # an unrelated comment contains a heart emoji.
        low=msg.casefold()
        if 'beni sev' in low or 'beni sev!' in low:
            self._love_users.add(u); return 'love'
        return 'normal'
    def color_for(self,cls): return {'normal':QColor('#ffffff'),'moderator':QColor('#ff4d4d'),'love':QColor('#ff9f1a'),'publisher':QColor('#b36bff'),'subscriber':QColor('#32d583')}.get(cls,QColor('#ffffff'))
    def role_icon(self, cls):
        # Chat'te gereksiz rol yazıları yerine tek, anlaşılır bir rol simgesi göster.
        # Normal kullanıcı sohbet balonu; yayıncı mikrofon; moderatör kalkan;
        # abone yıldız; "Beni Sev" sınıfı turuncu kalp kullanır.
        return {
            'publisher':'🎤',
            'moderator':'🛡️',
            'subscriber':'⭐',
            'love':'🧡',
            'normal':'💬',
        }.get(cls,'💬')
    def top_gifter_badges(self, limit=3):
        badges={}
        if not self.sid:
            return badges
        try:
            for i,row in enumerate(self.db.gifts(self.sid, max(3, limit)), 1):
                if i>limit:
                    break
                r=record_dict(row)
                u=str(r.get('user') or r.get('username') or '').strip().lower()
                if not u:
                    continue
                badges[u]='🥇 Top 1' if i==1 else ('🥈 Top 2' if i==2 else ('🥉 Top 3' if i==3 else f'{i}#'))
        except Exception:
            return {}
        return badges
    def chat_prefix(self, row, cls=None, gift_badges=None):
        cls = cls or self.classify(row)
        u = str(row.get('username') or row.get('user') or '').strip().lower()
        badge = (gift_badges or {}).get(u, '') if u else ''
        role_text={
            'publisher':'🎤 Yayıncı',
            'moderator':'🛡️ Moderatör',
            'subscriber':'⭐ Abone',
            'love':'🧡 Beni Sev',
            'normal':'💬',
        }.get(cls,'💬')
        if badge:
            return f'{role_text} {badge}'
        return role_text
    def _role_for_event(self,e):
        u=str(e.get('username','') or '').strip().lower()
        role=str(e.get('role','') or '').lower()
        if u and u==self.broadcaster_username:return 'publisher'
        if role=='moderator': self.moderators_set.add(u); return 'moderator'
        if role=='subscriber': self.subscribers_set.add(u); return 'subscriber'
        if u in self.moderators_set:return 'moderator'
        if u in self.subscribers_set:return 'subscriber'
        return ''

    def _should_read_chat(self,e):
        u=str(e.get('username','') or '').strip().lower()
        role=self._role_for_event(e)
        if self.settings.get('read_all',True):
            return True
        if role=='publisher': return bool(self.settings.get('read_publisher',True))
        if role=='moderator': return bool(self.settings.get('read_moderators',True))
        if role=='subscriber': return bool(self.settings.get('read_subscribers',True))
        if u in self.gifters_set and self.settings.get('read_gifters',True): return True
        if u in self.followers_set and self.settings.get('read_followers',True): return True
        return bool(self.settings.get('read_normal',True))

    def on_event(self,e):
        if not self.sid:return
        e=normalize_live_record(e)
        typ=e.get('type')
        if e.get('username') and e.get('avatar_url'):self.avatar_for(e['username'],e['avatar_url'])
        if typ=='connected': self.live_connected=True; self.set_status('BAĞLANDI • Room '+str(e.get('room_id','')))
        elif typ=='connection_error': self.live_connected=False; self.set_status('BAĞLANTI HATASI • '+str(e.get('error',''))); self.adapter=None; self.db.end_session(self.sid); self._set_connect_button('LIVE Bağlan', self.connect_live)
        elif typ=='disconnected': self.live_connected=False; self.set_status('BAĞLI DEĞİL • LIVE bağlantısı kapandı'); self._set_connect_button('LIVE Bağlan', self.connect_live)
        elif typ=='viewer' and e.get('viewer_source')=='room_user_seq':
            # RoomUserSeqEvent.viewer_count is the only concurrent-viewer source.
            # Never replace it with room-info totals, popularity, likes, or max views.
            try:n=int(e.get('viewer_count',0) or 0)
            except (TypeError,ValueError):n=0
            if n>0:
                import time
                self.last_room_viewer_at=time.monotonic()
                self.stats['viewers']=n
                self.stats['max']=max(self.stats['max'],n)
                self.status_detail.setText(f'LIVE • Anlık izleyici: {n:,} • Maksimum: {self.stats["max"]:,}')
        elif typ=='gift':
            meta=self.gift_catalog.resolve(e.get('gift_name',''))
            if meta:
                e['gift_image_url']=e.get('gift_image_url') or meta.get('image_url','')
                site_coins=int(meta.get('coins',0) or 0)
                if site_coins:
                    e['gift_coins']=site_coins
                    e['diamond_count']=site_coins*int(e.get('gift_count',1) or 1)
                elif not e.get('gift_coins'):
                    e['gift_coins']=int(e.get('diamond_count',0) or 0)
            if e.get('username'): self.gifters_set.add(str(e.get('username')).lower())
            self.stats['gifts']+=int(e.get('gift_count',0) or 0); self.stats['diamonds']+=int(e.get('diamond_count',0) or 0)
            if self.settings.get('sound_enabled') and self.settings.get('sound_gift'):play_event_sound('gift', self.settings.get('sound_file_gift',''), self.settings.get('sound_duration_gift',0))
        elif typ=='like':
            b=int(e.get('like_count',0) or 0); total=int(e.get('total_like_count',0) or 0); self.stats['likes']=max(self.stats['likes'],total) if total else self.stats['likes']+b
            if self.settings.get('sound_enabled') and self.settings.get('sound_like'):play_event_sound('like', self.settings.get('sound_file_like',''), self.settings.get('sound_duration_like',0))
        elif typ=='follow':
            if e.get('username'): self.followers_set.add(str(e.get('username')).lower())
            self.stats['follows']+=1
            if self.settings.get('sound_enabled') and self.settings.get('sound_follow'):play_event_sound('follow', self.settings.get('sound_file_follow',''), self.settings.get('sound_duration_follow',0))
        elif typ=='subscribe':
            u=str(e.get('username','') or '').lower()
            if u:self.subscribers_set.add(u)
        elif typ=='join':
            self.stats['joins'] = int(self.stats.get('joins',0)) + 1
        elif typ=='chat':
            self._role_for_event(e)
            self.stats['chats']+=1
            self.chat_cache.append(dict(e))
            if len(self.chat_cache)>3000:self.chat_cache=self.chat_cache[-3000:]
            if self._should_read_chat(e) and not (self.settings.get('ai_ignore_emotes') and e.get('chat_source')=='emote'):
                self.reader.speak(e.get('message'), username=e.get('username'), nickname=e.get('nickname'))
            if self.settings.get('sound_enabled') and self.settings.get('sound_chat'):play_event_sound('chat', self.settings.get('sound_file_chat',''), self.settings.get('sound_duration_chat',0))
        try:
            self.db.add_event(self.sid,typ,**e)
        except Exception as exc:
            # Keep the live chat visible even if a transient SQLite lock occurs.
            self.status_detail.setText(f'LIVE • SQLite bekliyor: {type(exc).__name__}')
        self.dirty=True
    def refresh(self):
        if self.freeze_view:return
        for k,v in self.stats.items():
            if k in self.card:self.card[k].setText(f'{int(v):,}')
        if self.stats['likes']>self.last_like_total and self.like.isVisible():self.like.play_heart()
        self.last_like_total=self.stats['likes']
        if self.dirty:
            try:
                self.refresh_tables(); self.dirty=False
            except Exception as exc:
                self.status_detail.setText(f'Liste yenileme hatası: {type(exc).__name__}: {exc}')
                try:
                    log=self.base/'data'/'ui_errors.log'; log.parent.mkdir(parents=True,exist_ok=True)
                    with log.open('a',encoding='utf-8') as fh: fh.write(f'{datetime.now().isoformat()} {type(exc).__name__}: {exc}\n')
                except Exception:
                    pass
    def toggle_freeze(self,c):self.freeze_view=bool(c);self.freeze_button.setText('🔒 Veri Sabit' if c else '🔓 Canlı Veri'); self.dirty=True if not c else self.dirty
    def force_refresh(self):self.dirty=True
    def refresh_tables(self):
        if not self.sid:return
        # General tab: recent live events, newest first.
        recent=[record_dict(r) for r in self.db.recent_events(self.sid,250)]
        rows=[]
        for i,r in enumerate(recent):
            typ=r.get('type',''); labels={'chat':'💬 Chat','gift':'🎁 Hediye','like':'❤️ Beğeni','follow':'👥 Takip','viewer':'👁 İzleyici','join':'🚪 Katıldı','connected':'🟢 Bağlandı','disconnected':'🔴 Koptu'}
            detail=r.get('message') or r.get('gift_name') or (str(r.get('like_count',0))+' beğeni' if r.get('like_count') else '') or (str(r.get('viewer_count',0))+' izleyici' if r.get('viewer_count') else '')
            rows.append([r.get('ts',''),r.get('user',''),labels.get(typ,typ),detail])
        self._sync_general_views(rows)

        # IMPORTANT: sqlite3.Row has no .get(). Always normalize before merging.
        chats=merge_chat_records(self.db.chats(self.sid,2000), self.chat_cache, 2000)
        top_gifter_badges=self.top_gifter_badges(3)
        self.chat_table.setUpdatesEnabled(False); self.chat_table.setRowCount(len(chats))
        for i,r in enumerate(chats):
            cls=self.classify(r); color=self.color_for(cls); user=display_user(r) or '@?'
            prefix=self.chat_prefix(r, cls, top_gifter_badges)
            a=QTableWidgetItem(f'{prefix} {user}'); a.setForeground(color); self.chat_table.setItem(i,0,a)
            self.chat_table.setItem(i,1,QTableWidgetItem(str(r.get('message',''))))
            self.chat_table.setItem(i,2,QTableWidgetItem(str(r.get('ts',''))))
        self.chat_table.setUpdatesEnabled(True)
        if chats:self.chat_table.scrollToBottom()

        gifts=[record_dict(r) for r in self.db.gifts(self.sid,100)]; self.gift_table.setRowCount(len(gifts)); grow=[]
        for i,r in enumerate(gifts,1):
            medal='🥇' if i==1 else ('🥈' if i==2 else ('🥉' if i==3 else f'{i}#')); meta=self.gift_catalog.resolve(r.get('gift_name',''))
            gift_img=meta.get('image_url','')
            user=display_user(r) or '@?'
            grow.append({'text':f'{medal} {user} • {r.get("gifts",0)} hediye • {r.get("diamonds",0)} puan','avatar':self.avatar_for(user,r.get('avatar_url','')),'image':gift_img})
            vals=[medal,user,r.get('gift_name') or '-',r.get('gifts',0),r.get('diamonds',0)]
            for j,val in enumerate(vals):
                item=QTableWidgetItem(str(val or ''))
                if j==1 and r.get('avatar_url'):
                    item.setIcon(QIcon(self.avatar_for(user,r.get('avatar_url',''))))
                self.gift_table.setItem(i-1,j,item)
        self.gift.set_styled_rows(grow)

        recent_gifts=[record_dict(r) for r in self.db.recent_gifts(self.sid,100)]; rg=[]
        for r in reversed(recent_gifts):
            meta=self.gift_catalog.resolve(r.get('gift_name',''))
            img=r.get('gift_image_url') or meta.get('image_url',''); coins=r.get('gift_coins') or meta.get('coins',0) or r.get('diamond_count',0)
            user=display_user(r) or '@?'
            rg.append({'text':f'🎁 {user} → {r.get("gift_name", "Gift")} ×{r.get("gift_count",1)} • {coins} 💎','avatar':self.avatar_for(user,r.get('avatar_url','')),'image':img})
        self.recent_gift.set_styled_rows(rg)

        likes=[record_dict(r) for r in self.db.likes(self.sid,100)]; self.like_table.setRowCount(len(likes)); like_rows=[]
        text_color=QColor(self.settings.get('like_text_color','#ff5b7f'))
        count_color=QColor(self.settings.get('like_count_color','#ffffff'))
        for i,r in enumerate(likes,1):
            medal='🥇' if i==1 else ('🥈' if i==2 else ('🥉' if i==3 else f'{i}#')); user=display_user(r) or '@?'
            avatar=self.avatar_for(user,r.get('avatar_url',''))
            like_rows.append({'rank':medal,'user':user,'likes':int(r.get('likes',0) or 0),'avatar':avatar})
            for j,val in enumerate([medal,user,r.get('likes',0)]):
                item=QTableWidgetItem(str(val)); item.setForeground(count_color if j==2 else text_color)
                if j==1 and avatar:item.setIcon(QIcon(avatar))
                self.like_table.setItem(i-1,j,item)
        self.like.set_like_rows(like_rows)

        fs=[record_dict(r) for r in self.db.followers(self.sid,since_for(self.filter.currentText()))]; self.follow_table.setRowCount(len(fs)); frows=[]
        for i,r in enumerate(fs):
            user=display_user(r) or '@?'
            self.follow_table.setItem(i,0,QTableWidgetItem(str(r.get('ts',''))));self.follow_table.setItem(i,1,QTableWidgetItem(user));frows.append({'text':f'{str(r.get("ts", ""))[11:19]} • {user}','avatar':self.avatar_for(user,r.get('avatar_url',''))})
        self.follow.set_styled_rows(frows)

        joins=[record_dict(r) for r in reversed(self.db.joins(self.sid,500))]
        self.join_table.setRowCount(len(joins))
        for i,r in enumerate(joins):
            user=display_user(r) or '@?'
            self.join_table.setItem(i,0,QTableWidgetItem(str(r.get('ts',''))))
            item=QTableWidgetItem(user)
            if r.get('avatar_url'):
                path=self.avatar_for(user,r.get('avatar_url',''))
                if path:item.setIcon(QIcon(path))
            self.join_table.setItem(i,1,item)
        if joins:self.join_table.scrollToBottom()

        chat_rows=chats[-150:]
        overlay_rows=[]
        for r in chat_rows:
            cls=self.classify(r)
            user=display_user(r) or '@?'
            overlay_rows.append({
                'user':user,
                'message':str(r.get('message','') or ''),
                'avatar':self.avatar_for(user,r.get('avatar_url','')),
                'cls':cls,
                'badge':top_gifter_badges.get(str(r.get('username') or r.get('user') or '').strip().lower(),''),
                'color':self.color_for(cls).name(),
            })
        self.chat.set_rows(overlay_rows)

    def chat_style(self):
        return {
            'align':self.settings.get('chat_align','left'),
            'text_color':self.settings.get('chat_text_color','#ffffff'),
            'rgb_text':bool(self.settings.get('chat_rgb_text',False)),
            'wave_text':bool(self.settings.get('chat_wave_text',False)),
            'glow_text':bool(self.settings.get('chat_glow_text',False)),
            'avatar_size':int(self.settings.get('chat_avatar_size',34) or 34),
            'row_gap':int(self.settings.get('chat_row_gap',8) if self.settings.get('chat_row_gap',8) is not None else 8),
            'show_avatar':bool(self.settings.get('chat_show_avatar',True)),
            'show_title':bool(self.settings.get('chat_show_title',True)),
            'bg_alpha':int(self.settings.get('chat_bg_alpha',48) if self.settings.get('chat_bg_alpha',48) is not None else 48),
            'font_size':int(self.settings.get('chat_font_size',18) or 18),
            'title_size':int(self.settings.get('chat_title_size',20) or 20),
            'width':int(self.settings.get('chat_widget_width',480) or 480),
            'height':int(self.settings.get('chat_widget_height',800) or 800),
        }

    def like_style(self):
        return {
            'align':self.settings.get('like_align','left'),
            'text_color':self.settings.get('like_text_color','#ff5b7f'),
            'count_color':self.settings.get('like_count_color','#ffffff'),
            'heart_color':self.settings.get('like_heart_color','#ff2f67'),
            'rgb_text':bool(self.settings.get('like_rgb_text',False)),
            'wave_text':bool(self.settings.get('like_wave_text',False)),
            'glow_text':bool(self.settings.get('like_glow_text',True)),
            'avatar_size':int(self.settings.get('like_avatar_size',34) or 34),
            'row_gap':int(self.settings.get('like_row_gap',6) if self.settings.get('like_row_gap',6) is not None else 6),
            'show_avatar':bool(self.settings.get('like_show_avatar',True)),
            'show_title':bool(self.settings.get('like_show_title',True)),
            'bg_alpha':int(self.settings.get('like_bg_alpha',48) if self.settings.get('like_bg_alpha',48) is not None else 48),
        }

    def gift_style(self):
        return {
            'align':self.settings.get('gift_align','left'),
            'text_color':self.settings.get('gift_text_color','#ffd166'),
            'rgb_text':bool(self.settings.get('gift_rgb_text',False)),
            'wave_text':bool(self.settings.get('gift_wave_text',False)),
            'glow_text':bool(self.settings.get('gift_glow_text',True)),
            'avatar_size':int(self.settings.get('gift_avatar_size',34) or 34),
            'row_gap':int(self.settings.get('gift_row_gap',6) if self.settings.get('gift_row_gap',6) is not None else 6),
            'show_avatar':bool(self.settings.get('gift_show_avatar',True)),
            'show_title':bool(self.settings.get('gift_show_title',True)),
            'bg_alpha':int(self.settings.get('gift_bg_alpha',48) if self.settings.get('gift_bg_alpha',48) is not None else 48),
        }

    def follow_style(self):
        return {
            'align':self.settings.get('follow_align','left'),
            'text_color':self.settings.get('follow_text_color','#ffffff'),
            'rgb_text':bool(self.settings.get('follow_rgb_text',False)),
            'wave_text':bool(self.settings.get('follow_wave_text',False)),
            'glow_text':bool(self.settings.get('follow_glow_text',False)),
            'avatar_size':int(self.settings.get('follow_avatar_size',34) or 34),
            'row_gap':int(self.settings.get('follow_row_gap',6) if self.settings.get('follow_row_gap',6) is not None else 6),
            'show_avatar':bool(self.settings.get('follow_show_avatar',True)),
            'show_title':bool(self.settings.get('follow_show_title',True)),
            'bg_alpha':int(self.settings.get('follow_bg_alpha',48) if self.settings.get('follow_bg_alpha',48) is not None else 48),
        }

    def test_browser_source(self, mode):
        """Show temporary sample rows in one Browser Source for five seconds."""
        mode=str(mode or '').strip()
        if mode not in {'chat','gifts','recent-gifts','likes','followers','joins','viewers'}:
            return
        self.browser_test_until[mode]=time.monotonic()+5.0
        self.status_detail.setText(f'🧪 {mode} Browser Source testi • 5 saniye')
        QTimer.singleShot(5100, lambda m=mode:self._finish_browser_test(m))

    def _finish_browser_test(self, mode):
        expiry=self.browser_test_until.get(mode,0)
        if expiry and time.monotonic()>=expiry:
            self.browser_test_until.pop(mode,None)
            self.status_detail.setText('Browser Source testi tamamlandı.')

    @staticmethod
    def _browser_demo_rows(mode):
        if mode=='chat':
            return [
                {'user':'Yayıncı','message':'Yayıncı test mesajı','cls':'publisher','icon':'🎤','badge':'🥇 Top 1','avatar':'','ts':'TEST-1'},
                {'user':'Moderatör','message':'Moderatör test mesajı','cls':'moderator','icon':'🛡️','badge':'🥈 Top 2','avatar':'','ts':'TEST-2'},
                {'user':'Abone','message':'Abone test mesajı','cls':'subscriber','icon':'⭐','badge':'🥉 Top 3','avatar':'','ts':'TEST-3'},
                {'user':'Beni Sev','message':'Beni sev rolü test mesajı','cls':'love','icon':'🧡','badge':'','avatar':'','ts':'TEST-4'},
                {'user':'Normal Kullanıcı','message':'Normal kullanıcı test mesajı','cls':'normal','icon':'💬','badge':'','avatar':'','ts':'TEST-5'},
            ]
        if mode=='gifts':
            return [
                {'rank':'🥇','user':'Top Gifter 1','value':'125 hediye • 12500 puan','cls':'normal','avatar':''},
                {'rank':'🥈','user':'Top Gifter 2','value':'84 hediye • 8200 puan','cls':'normal','avatar':''},
                {'rank':'🥉','user':'Top Gifter 3','value':'61 hediye • 5700 puan','cls':'normal','avatar':''},
            ]
        if mode=='recent-gifts':
            return [
                {'user':'Demo Kullanıcı','gift':'Rose','count':5,'coins':5,'image':'','avatar':'','cls':'normal'},
                {'user':'Demo Destekçi','gift':'Galaxy','count':1,'coins':1000,'image':'','avatar':'','cls':'normal'},
            ]
        if mode=='likes':
            return [
                {'rank':'🥇','user':'Beğeni Lideri','value':'12.345 ❤️','likes':12345,'cls':'normal','avatar':''},
                {'rank':'🥈','user':'İkinci Kullanıcı','value':'8.765 ❤️','likes':8765,'cls':'normal','avatar':''},
                {'rank':'🥉','user':'Üçüncü Kullanıcı','value':'5.432 ❤️','likes':5432,'cls':'normal','avatar':''},
            ]
        if mode=='followers':
            return [
                {'rank':'','user':'Yeni Takipçi 1','value':'şimdi','cls':'normal','avatar':''},
                {'rank':'','user':'Yeni Takipçi 2','value':'şimdi','cls':'normal','avatar':''},
            ]
        if mode=='joins':
            return [
                {'rank':'','user':'Yayına Katılan 1','value':'şimdi','cls':'normal','avatar':''},
                {'rank':'','user':'Yayına Katılan 2','value':'şimdi','cls':'normal','avatar':''},
            ]
        return []

    def _apply_browser_test_data(self, snap):
        now=time.monotonic()
        for mode,expiry in list(self.browser_test_until.items()):
            if now>=expiry:
                self.browser_test_until.pop(mode,None)
                continue
            if mode=='viewers':
                snap['viewers']=246
                snap['max']=512
            else:
                snap[mode]=self._browser_demo_rows(mode)
        return snap

    def browser_snapshot(self):
        snap=build_browser_snapshot(
            self.db, self.sid, self.stats, self.chat_cache,
            self.classify, self.gift_catalog.resolve
        )
        snap['widget_style']=self.like_style()  # backward compatibility
        snap['widget_styles']={
            'chat':self.chat_style(),
            'all':self.chat_style(),
            'likes':self.like_style(),
            'gifts':self.gift_style(),
            'recent-gifts':self.gift_style(),
            'followers':self.follow_style(),
            'joins':self.follow_style(),
        }
        return self._apply_browser_test_data(snap)

    def _show(self,w):w.show();w.raise_();w.activateWindow()
    def show_chat(self):self._show(self.chat)
    def show_gift(self):self._show(self.gift)
    def show_recent_gift(self):self._show(self.recent_gift)
    @staticmethod
    def _all_image_urls_from_value(value):
        """Collect every HTTP(S) URL from common TikTok/Euler image objects."""
        out=[]
        def add(v):
            if isinstance(v,str):
                v=v.strip()
                if v.startswith(('http://','https://')) and v not in out:
                    out.append(v)
            elif isinstance(v,(list,tuple)):
                for item in v:
                    add(item)
            elif isinstance(v,dict):
                # URL-bearing fields first, then nested values.
                for key in ('url_list','urlList','urls','url','download_url','downloadUrl','uri'):
                    if key in v:
                        add(v.get(key))
                for item in v.values():
                    if isinstance(item,(dict,list,tuple)):
                        add(item)
        add(value)
        return out

    @staticmethod
    def _image_url_from_value(value):
        urls=MainWindow._all_image_urls_from_value(value)
        return urls[0] if urls else ''

    @classmethod
    def _avatar_urls_from_profile(cls, payload):
        """Return all avatar/profile-photo URLs from an Euler response.

        We intentionally do not trust field names such as avatarLarger to mean
        a specific pixel size. TikTok response variants change over time, so the
        downloader later decodes every candidate and selects the largest image by
        its *real* dimensions.
        """
        found=[]
        preferred_keys={
            'avatarlarger','avatar_larger','avatarlarge','avatar_large',
            'avatarmedium','avatar_medium','profilepicture','profile_picture',
            'avatarurl','avatar_url','avatarthumb','avatar_thumb','avatar',
            'profileimage','profile_image','profilephoto','profile_photo',
        }
        def add_url(url):
            if url and url not in found:
                found.append(url)
        def walk(obj, parent_key=''):
            if isinstance(obj,dict):
                # First collect explicit avatar/profile keys.
                for key,val in obj.items():
                    k=str(key).casefold()
                    compact=re.sub(r'[^a-z0-9_]+','',k)
                    is_avatar=(compact in preferred_keys or 'avatar' in compact or
                               (('profile' in compact) and any(x in compact for x in ('pic','image','photo'))))
                    if is_avatar:
                        for url in cls._all_image_urls_from_value(val):
                            add_url(url)
                # Then recurse so wrapped user/data/response objects are covered.
                for key,val in obj.items():
                    if isinstance(val,(dict,list,tuple)):
                        walk(val,str(key))
            elif isinstance(obj,(list,tuple)):
                for val in obj:
                    walk(val,parent_key)
        walk(payload)
        return found

    @classmethod
    def _best_avatar_url_from_profile(cls, payload):
        urls=cls._avatar_urls_from_profile(payload)
        return urls[0] if urls else ''

    @staticmethod
    def _numeric_tiktok_user_id(payload):
        """Extract the numeric TikTok user id used by Euler's full user endpoint."""
        wanted=('id','uid','user_id','userid','id_str','idstr')
        best=''
        def walk(obj, in_user=False):
            nonlocal best
            if best:
                return
            if isinstance(obj,dict):
                for key,val in obj.items():
                    k=str(key).casefold().replace('-','_')
                    user_ctx=in_user or k in ('user','author','profile','data','response','result')
                    if k in wanted:
                        s=str(val or '').strip()
                        # TikTok numeric ids are large decimal strings. Requiring at
                        # least 8 digits avoids picking counters/room flags.
                        if s.isdigit() and len(s)>=8:
                            best=s; return
                    if isinstance(val,(dict,list,tuple)):
                        walk(val,user_ctx)
                        if best: return
            elif isinstance(obj,(list,tuple)):
                for val in obj:
                    walk(val,in_user)
                    if best: return
        walk(payload)
        return best

    @staticmethod
    def _euler_cdn_variants(url):
        """Create stable Euler Image-CDN variants, including largest stored asset.

        Euler documents that after an asset is stored, the TikTok hostname/query
        can be dropped, and the ~tplv variant suffix may be dropped to serve the
        largest stored variant. We only apply this transformation to Euler CDN
        hosts; origin TikTok URLs are never rewritten.
        """
        url=str(url or '').strip()
        try:
            u=urlsplit(url)
        except Exception:
            return []
        host=(u.hostname or '').casefold()
        if not host.endswith('.assets.cdn.eulerstream.com'):
            return []
        parts=[x for x in u.path.split('/') if x]
        # Signed first-request form starts with the upstream TikTok CDN hostname.
        if parts and ('tiktokcdn' in parts[0].casefold() or 'tiktokcdn-' in parts[0].casefold()):
            parts=parts[1:]
        if not parts:
            return []
        exact='/'+'/'.join(parts)
        # Largest stored variant: remove ~tplv... suffix from final asset key.
        largest=re.sub(r'~tplv-[^/]+$','',exact,flags=re.I)
        # Some variants include a normal extension after the tplv token; keep the
        # base asset path even when that means it has no extension (Euler accepts it).
        variants=[]
        for path in (largest,exact):
            candidate=urlunsplit((u.scheme,u.netloc,path,'',''))
            if candidate not in variants:
                variants.append(candidate)
        return variants

    @staticmethod
    def _to_euler_proxy_url(url):
        """Route TikTok CDN assets through Euler's CDN proxy without changing path/query."""
        url=str(url or '').strip()
        if not url:
            return ''
        try:
            u=urlsplit(url)
        except Exception:
            return ''
        host=(u.hostname or '').strip()
        low=host.casefold()
        if not host or 'tiktokcdn' not in low:
            return ''
        if low.endswith('.cdn-proxy.eulerstream.com'):
            return url
        proxied_host=host+'.cdn-proxy.eulerstream.com'
        if u.port:
            proxied_host += ':'+str(u.port)
        return urlunsplit((u.scheme or 'https',proxied_host,u.path,u.query,u.fragment))

    @classmethod
    def _avatar_1080_variants(cls, url):
        """Best-effort 1080x1080 TikTok avatar variants.

        TikTok avatar URLs often encode a crop/resize size in the tplv suffix.
        We try a 1080x1080 form and the same URL through Euler's public CDN proxy.
        If TikTok rejects the rewritten signed URL, the original candidate remains
        available and is used as fallback.
        """
        url=str(url or '').strip()
        if not url:
            return []
        variants=[]
        def add(v):
            v=str(v or '').strip()
            if v.startswith(('http://','https://')) and v not in variants:
                variants.append(v)
        add(url)

        # Common TikTok forms:
        #   ...~tplv-tiktokx-cropcenter:300:300.webp
        #   ...~tplv-...:720:720.jpeg
        #   .../300x300/...
        rewritten=re.sub(
            r':(?:72|96|100|108|128|144|168|200|240|256|300|320|360|480|512|640|720|750|800|900|960|1024):(?:72|96|100|108|128|144|168|200|240|256|300|320|360|480|512|640|720|750|800|900|960|1024)(?=\.(?:webp|jpe?g|png)(?:[?#]|$))',
            ':1080:1080', url, flags=re.I)
        rewritten=re.sub(r'(?<!\d)(?:72|96|100|108|128|144|168|200|240|256|300|320|360|480|512|640|720|750|800|900|960|1024)x(?:72|96|100|108|128|144|168|200|240|256|300|320|360|480|512|640|720|750|800|900|960|1024)(?!\d)', '1080x1080', rewritten, flags=re.I)
        if rewritten != url:
            add(rewritten)

        # Euler proxy keeps signed TikTok URLs reachable even when direct CDN
        # access is flaky/expired. Try both original and requested-1080 variants.
        for candidate in list(variants):
            add(cls._to_euler_proxy_url(candidate))
        return variants

    @staticmethod
    def _save_avatar_as_1080(blob, path):
        """Decode source bytes and save an exact 1080x1080 HQ preview cache.

        If the upstream source itself is smaller than 1080, this only performs a
        high-quality upscale; it cannot invent source detail. Metadata keeps the
        true upstream dimensions so the distinction remains auditable.
        """
        pix=QPixmap()
        if not pix.loadFromData(blob) or pix.isNull():
            return False
        target=HQ_AVATAR_TARGET
        scaled=pix.scaled(target,target,Qt.KeepAspectRatioByExpanding,Qt.SmoothTransformation)
        x=max(0,(scaled.width()-target)//2)
        y=max(0,(scaled.height()-target)//2)
        square=scaled.copy(x,y,target,target)
        return bool(square.save(str(path),'PNG',100))

    def _euler_profile_payloads(self, user, key):
        """Fetch Euler basic + full profile, trying current compatible API hosts."""
        user=str(user or '').strip().lstrip('@')
        if not user or not key:
            return []
        payloads=[]
        # Euler's current SDK documentation uses api.eulerstream.com; older/live
        # deployments use tiktok.eulerstream.com. Trying both keeps existing users
        # working across endpoint migrations.
        bases=('https://api.eulerstream.com','https://tiktok.eulerstream.com')
        # ORIGIN gives the signed TikTok source. CDN may expose stored variants and
        # lets us ask Euler's Image CDN for the largest stored source.
        image_sources=('ORIGIN','CDN')
        for base in bases:
            base_payloads=[]
            numeric=''
            for image_source in image_sources:
                headers={'X-Api-Key':key,'Accept':'application/json','x-image-source':image_source}
                try:
                    url=f'{base}/tiktok/users/{quote(user,safe="")}/basic'
                    r=requests.get(url,headers=headers,timeout=7)
                    if r.status_code==200:
                        data=r.json()
                        if isinstance(data,dict):
                            base_payloads.append(data)
                            numeric=numeric or self._numeric_tiktok_user_id(data)
                except Exception:
                    pass
                if numeric:
                    try:
                        url=f'{base}/tiktok/users/{quote(numeric,safe="")}'
                        r=requests.get(url,headers=headers,timeout=7)
                        if r.status_code==200:
                            data=r.json()
                            if isinstance(data,dict):
                                base_payloads.append(data)
                    except Exception:
                        pass
            if base_payloads:
                payloads.extend(base_payloads)
                # V53: keep checking the compatibility host too. Some Euler/TikTok
                # routes can expose different avatar variants, and for the large
                # preview we prefer one extra profile request over accepting a
                # 72/100 px thumbnail as the final source.
        return payloads

    @staticmethod
    def _download_avatar_candidate(url, key=''):
        """Download an avatar candidate and return (bytes, width, height)."""
        url=str(url or '').strip()
        if not url:
            return None
        headers={'User-Agent':'Mozilla/5.0','Accept':'image/avif,image/webp,image/apng,image/*,*/*;q=0.8'}
        if '.eulerstream.com' in url.casefold() and key:
            headers['X-Api-Key']=key
        try:
            r=requests.get(url,headers=headers,timeout=8)
            r.raise_for_status()
            blob=r.content
            if len(blob)<512:
                return None
            pix=QPixmap()
            if not pix.loadFromData(blob) or pix.isNull():
                return None
            return blob,int(pix.width()),int(pix.height())
        except Exception:
            return None

    def _cached_hq_avatar(self, user, min_side=HQ_AVATAR_TARGET, max_age_hours=12):
        """Reuse cache only when the *downloaded upstream source* was native 1080+.

        A 100x100 avatar that was merely upscaled to a 1080 PNG is intentionally
        not treated as an HQ source anymore. This forces a fresh Euler lookup on
        the next preview click until a genuinely large TikTok/Euler asset is found.
        """
        safe=hashlib.sha1(str(user or '').casefold().encode('utf-8','ignore')).hexdigest()
        path=self.avatar_hq_dir/f'{safe}.png'
        meta_path=self.avatar_hq_dir/f'{safe}.json'
        legacy=self.avatar_hq_dir/f'{safe}.img'
        try:
            if legacy.exists(): legacy.unlink()
        except Exception:
            pass
        if not path.exists() or path.stat().st_size<512 or not meta_path.exists():
            return ''
        try:
            meta=json.loads(meta_path.read_text(encoding='utf-8'))
            source_w=int(meta.get('source_width') or 0)
            source_h=int(meta.get('source_height') or 0)
            native=bool(meta.get('native_1080')) and min(source_w,source_h)>=int(min_side)
            age=(time.time()-path.stat().st_mtime)/3600.0
            pix=QPixmap()
            if native and pix.loadFromData(path.read_bytes()) and not pix.isNull():
                if min(pix.width(),pix.height())>=int(min_side) and age<=float(max_age_hours):
                    return str(path)
        except Exception:
            pass
        return ''

    def _download_hq_avatar(self, user, fallback_url=''):
        """Fetch the highest-resolution avatar Euler can provide and cache it.

        Flow:
          1) Euler /tiktok/users/{unique_id}/basic
          2) Extract numeric user id and query /tiktok/users/{numeric_user_id}
          3) Query ORIGIN and Euler CDN image sources
          4) For Euler CDN URLs also try the documented "largest stored variant"
          5) Generate/try TikTok 1080x1080 avatar variants through Euler proxy.
          6) Decode up to 96 candidates and prefer a native >=1080 source.
          7) Save a native-1080 cache only when the upstream source itself is >=1080.
             Smaller upstream images are kept in a separate fallback cache and are
             never reused as if they were native HQ.
        """
        user=str(user or '').strip().lstrip('@')
        fallback_url=str(fallback_url or '').strip()
        key=str(self.settings.get('euler_api_key','') or '').strip()

        cached=self._cached_hq_avatar(user)
        if cached:
            return cached

        candidates=[]
        def add(url):
            url=str(url or '').strip()
            if url and url.startswith(('http://','https://')) and url not in candidates:
                candidates.append(url)

        # Euler is authoritative for the large preview. Event thumbnail is only a
        # final fallback when Euler cannot return the user profile.
        if user and key:
            for payload in self._euler_profile_payloads(user,key):
                for url in self._avatar_urls_from_profile(payload):
                    # Ask for / prefer a 1080x1080 TikTok avatar form first, then
                    # keep Euler's largest stored CDN variant as a fallback.
                    for variant in self._avatar_1080_variants(url):
                        add(variant)
                    for variant in self._euler_cdn_variants(url):
                        add(variant)
                        for v1080 in self._avatar_1080_variants(variant):
                            add(v1080)
        for variant in self._avatar_1080_variants(fallback_url):
            add(variant)

        if not candidates:
            return ''

        # Limit requests defensively, but evaluate enough variants to avoid picking
        # avatarThumb merely because it appeared first in the response.
        candidates=candidates[:96]
        best_blob=None; best_url=''; best_w=0; best_h=0
        for url in candidates:
            got=self._download_avatar_candidate(url,key)
            if not got:
                continue
            blob,w,h=got
            # Prefer true image area, then shortest side. This reliably beats a
            # 72x72/100x100 thumbnail when Euler returns 300/720px variants.
            # Strongly prefer a native source whose shortest side reaches 1080.
            # Among equally suitable sources choose the largest real pixel area.
            native_1080 = 1 if min(w,h) >= HQ_AVATAR_TARGET else 0
            best_native_1080 = 1 if min(best_w,best_h) >= HQ_AVATAR_TARGET else 0
            score=(native_1080,w*h,min(w,h),max(w,h),len(blob))
            best_score=(best_native_1080,best_w*best_h,min(best_w,best_h),max(best_w,best_h),len(best_blob or b''))
            if best_blob is None or score>best_score:
                best_blob,best_url,best_w,best_h=blob,url,w,h

        if best_blob:
            safe=hashlib.sha1(user.casefold().encode('utf-8','ignore')).hexdigest()
            native_1080=bool(min(best_w,best_h)>=HQ_AVATAR_TARGET)
            # Keep native-HQ and fallback-upscale caches separate. A low-resolution
            # fallback must never masquerade as the native 1080 source on a later run.
            path=self.avatar_hq_dir/(f'{safe}.png' if native_1080 else f'{safe}_upscaled.png')
            try:
                if not self._save_avatar_as_1080(best_blob,path):
                    return best_url
                meta={
                    'user':user,
                    'source_url':best_url,
                    'source_width':best_w,
                    'source_height':best_h,
                    'output_width':HQ_AVATAR_TARGET,
                    'output_height':HQ_AVATAR_TARGET,
                    'preview_mode':'native_1080' if native_1080 else 'upscaled_fallback',
                    'native_1080':native_1080,
                    'updated_at':datetime.now().isoformat(timespec='seconds'),
                    'provider':'EulerStream',
                }
                (self.avatar_hq_dir/f'{safe}.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf-8')
                return str(path)
            except Exception:
                pass
            return best_url
        return fallback_url

    def preview_table_image(self,row,col):
        """Open the clicked user's avatar using the highest quality source available."""
        try:
            record=None
            if self.sender() is self.gift_table and col==1:
                record=self.db.gifts(self.sid,100)[row]
            elif self.sender() is self.like_table and col==1:
                record=self.db.likes(self.sid,100)[row]
            elif self.sender() is self.follow_table and col==1:
                record=self.db.followers(self.sid,since_for(self.filter.currentText()))[row]
            if record is None:
                return
            user=str(record['user'] or '')
            remote=str(record['avatar_url'] or '')
            # Never enlarge the small-icon cache first. Resolve/download a dedicated
            # high-quality avatar from the user's Euler profile when possible.
            source=self._download_hq_avatar(user,remote)
            if not source:
                # Final fallback for offline mode / missing API key.
                source=self.avatar_for(user,remote) or remote
            if not source:
                QMessageBox.information(self,'Profil fotoğrafı','Bu kullanıcı için profil fotoğrafı bulunamadı.')
                return
            from ui.overlay import ImagePreview
            ImagePreview(source,f'Profil • {user}',self).exec()
        except Exception as exc:
            QMessageBox.warning(self,'Profil fotoğrafı',f'Profil fotoğrafı açılamadı: {type(exc).__name__}: {exc}')
    def show_like(self):self._show(self.like)
    def show_follow(self):self._show(self.follow)
    def show_all(self):
        for w in [self.chat,self.gift,self.recent_gift,self.like,self.follow]:self._show(w)
    def pdf(self):
        if not self.sid:QMessageBox.warning(self,'PDF','Önce LIVE bağlanın veya Demo kullanın.');return
        self.db.flush(); default=self.data_dir/'reports'/f'live_{datetime.now():%Y%m%d_%H%M%S}.pdf'; path,_=QFileDialog.getSaveFileName(self,'PDF kaydet',str(default),'PDF (*.pdf)')
        if path:
            try:make_report(self.db,self.sid,path);QMessageBox.information(self,'PDF','Rapor oluşturuldu.')
            except Exception as e:QMessageBox.critical(self,'PDF Hatası',str(e))
    def demo(self):
        if self.sid:self.stop_live()
        self.sid=self.db.start_session('demo_creator','DEMO'); names=['Mert','Ayşe','Ahmet','Mehmet','Zeynep','Can','Ece'];
        for _ in range(150):
            n=random.choice(names); typ=random.choice(['chat']*6+['gift','like','follow','viewer']); base={'username':n.lower(),'nickname':n,'role':random.choice(['','moderator','subscriber']) if typ=='chat' else ''}
            if typ=='chat':base['message']=random.choice(['Selam!','Beni sev ❤️','Harika yayın!','😂😂'])
            elif typ=='gift':base.update(gift_name='Rose',gift_count=random.randint(1,10),diamond_count=random.randint(1,100))
            elif typ=='like':base['like_count']=random.randint(1,50)
            elif typ=='follow':pass
            else:base={'viewer_count':random.randint(200,3000)}
            self.db.add_event(self.sid,typ,**base)
        self.db.flush();self.dirty=True;self.set_status('DEMO');self.refresh()
    def closeEvent(self,e):
        if self.adapter:self.adapter.stop()
        if self.sid:self.db.end_session(self.sid)
        self.reader.stop()
        for w in [self.chat,self.gift,self.recent_gift,self.like,self.follow]:w.close()
        self.browser.stop(); self.db.close(); e.accept()
        if self._logout_requested and callable(self.logout_callback):
            QTimer.singleShot(80,self.logout_callback)
        elif not self._logout_requested:
            app=QApplication.instance()
            if app:
                QTimer.singleShot(0,app.quit)
