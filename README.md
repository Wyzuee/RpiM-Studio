# RπM Studio

TikTok LIVE yayınları için masaüstü kontrol uygulaması.

## Beta v1.0.0 — İlk sürüm

- **Windows hazır:** `RpiM_Studio_Beta_v1.0.0_Setup.exe`
- **macOS:** DMG paketi henüz yayımlanmadı.

[Windows & MacOS kurulum dosyasını Releases sayfasından indir](https://github.com/Wyzuee/RpiM-Studio/releases/latest)

> Bu depo yalnızca yayın, kurulum ve güncelleme sayfasıdır. Kaynak kodu burada yayımlanmaz.

## Windows kurulumu

1. **Releases** sayfasındaki `RpiM_Studio_Beta_v1.0.0_Setup.exe` dosyasını indirin.
2. Dosyayı çalıştırın ve kurulum sihirbazını tamamlayın.
3. Uygulamayı açın, giriş yapın ve TikTok yayıncı adınızı kontrol edin.

## macOS kurulumu

macOS için DMG yayımlandığında aynı Releases sayfasında şu adla yer alır:

`RpiM_Studio_Beta_vX.Y.Z_macOS.dmg`

## Euler API kurulumu

1. Uygulamada **Ayarlar → Bağlantı** bölümünü açın.
2. **Euler hesabı aç** düğmesiyle EulerStream hesabınızı oluşturun veya mevcut hesabınıza girin.
3. EulerStream panelinden API anahtarınızı alın.
4. Anahtarı uygulamadaki **Euler API Key** alanına yapıştırıp kaydedin.
5. Ana ekranda **TikTok LIVE’a bağlan** düğmesine basın.

API anahtarı yalnızca sizin cihazınızda saklanır.

## Güncellemeler

Uygulama açılışta GitHub Releases alanını kontrol eder. İlk Beta sürümünden sonra numaralandırma şu şekilde devam eder:

- Beta v1.0.0
- Beta v1.0.1
- Beta v1.0.2

Her sürümde Release etiketi `vX.Y.Z` olmalı ve yalnız işletim sistemine uygun kurulum dosyası yüklenmelidir:

- Windows: `RpiM_Studio_Beta_vX.Y.Z_Setup.exe`
- macOS: `RpiM_Studio_Beta_vX.Y.Z_macOS.dmg`

Windows ve macOS dosyaları aynı yayın altında bulunabilir. Uygulama kendi işletim sistemine uygun paketi otomatik seçer.
