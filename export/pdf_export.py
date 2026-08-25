from pathlib import Path
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

def make_report(db, sid, path):
    path = Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    font="Helvetica"; bold="Helvetica-Bold"
    try:
        pdfmetrics.registerFont(TTFont("ArialTR",r"C:\Windows\Fonts\arial.ttf"))
        pdfmetrics.registerFont(TTFont("ArialTRBold",r"C:\Windows\Fonts\arialbd.ttf"))
        font="ArialTR"; bold="ArialTRBold"
    except Exception:
        pass

    styles=getSampleStyleSheet()
    styles["Title"].fontName=bold
    styles["BodyText"].fontName=font
    styles["Heading2"].fontName=bold
    s=db.session(sid); m=db.summary(sid)
    doc=SimpleDocTemplate(str(path),pagesize=A4)
    story=[
        Paragraph("RπM Studio • TikTok LIVE Yayın Raporu",styles["Title"]),Spacer(1,10),
        Paragraph(f"Yayıncı: @{s.get('username','')}",styles["BodyText"]),
        Paragraph(f"Başlangıç: {s.get('started_at','')}",styles["BodyText"]),
        Paragraph(f"Bitiş: {s.get('ended_at') or 'Devam ediyor'}",styles["BodyText"]),
        Spacer(1,12)
    ]
    rows=[["Metrik","Değer"],
          ["Toplam hediye",m["gifts"]],["Toplam elmas/puan",m["diamonds"]],
          ["Toplam beğeni",m["likes"]],["Yeni takipçi",m["follows"]],
          ["Chat mesajı",m["chats"]],["Maksimum izleyici",m["max_viewers"]]]
    t=Table(rows,colWidths=[260,180],repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,0),colors.HexColor("#22252b")),
        ("TEXTCOLOR",(0,0),(-1,0),colors.white),
        ("GRID",(0,0),(-1,-1),0.4,colors.grey),("FONTNAME",(0,0),(-1,0),bold),
        ("FONTNAME",(0,1),(-1,-1),font),("PADDING",(0,0),(-1,-1),7)
    ]))
    story += [t,PageBreak(),Paragraph("En Çok Hediye Atanlar",styles["Heading2"]),Spacer(1,8)]
    rows=[["#","Kullanıcı","Hediye","Puan"]]
    for i,r in enumerate(db.gifts(sid,100),1):
        rows.append([i,r["user"],r["gifts"],r["diamonds"]])
    t=Table(rows,repeatRows=1,colWidths=[35,240,90,90])
    t.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,0),colors.HexColor("#22252b")),
        ("TEXTCOLOR",(0,0),(-1,0),colors.white),
        ("GRID",(0,0),(-1,-1),0.4,colors.grey),("FONTNAME",(0,0),(-1,0),bold),
        ("FONTNAME",(0,1),(-1,-1),font),("PADDING",(0,0),(-1,-1),5)
    ]))
    story.append(t)
    story += [Spacer(1,14),Paragraph("En Çok Beğeni Atanlar",styles["Heading2"]),Spacer(1,8)]
    rows=[["#","Kullanıcı","Beğeni"]]
    for i,r in enumerate(db.likes(sid,100),1):
        rows.append([i,r["user"],r["likes"]])
    story.append(Table(rows,repeatRows=1,colWidths=[35,270,120]))
    story += [PageBreak(),Paragraph("Zamana Göre Hediye",styles["Heading2"]),Spacer(1,8)]
    rows=[["Saat","Hediye","Puan"]]
    for r in db.hourly_gifts(sid):
        rows.append([r["hour"],r["gifts"],r["diamonds"]])
    story.append(Table(rows,repeatRows=1,colWidths=[180,100,100]))
    doc.build(story)
    return path
