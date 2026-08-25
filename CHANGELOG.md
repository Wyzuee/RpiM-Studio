# RπM Studio v53

- Profil önizlemede Euler üzerinden native 1080+ kaynak araması sıkılaştırıldı.
- Düşük çözünürlüklü bir kaynağın 1080'e büyütülmüş cache'i artık native HQ olarak tekrar kullanılmıyor.
- Euler'ın iki uyumlu kullanıcı API hostu ve ORIGIN/CDN avatar adayları birlikte taranıyor; 96 adaya kadar gerçek piksel ölçümü yapılıyor.
- Native 1080 yoksa arayüz bunu açıkça belirtiyor ve mevcut en yüksek kaynağı 1080 çıktıya ölçekliyor.
- Eski changelog/test/__pycache__ dosyaları dağıtım paketinden temizlendi.
- Tek cross-platform release builder eklendi: Windows'ta Setup EXE, macOS'ta .app + DMG üretir.
- macOS application data yolu ~/Library/Application Support/RpiM Studio olarak düzenlendi.
