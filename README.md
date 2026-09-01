# RπM Studio

TikTok LIVE yayınları için masaüstü kontrol uygulaması.

## İndir — Beta v1.0.1

Güncel dağıtım paketi GitHub Releases sayfasında iki işletim sistemi için ayrı dosya olarak bulunur:

- **Windows:** [RpiM_Studio_Beta_v1.0.1_Setup.exe](https://github.com/Wyzuee/RpiM-Studio/releases/download/V1.0.1/RpiM_Studio_Beta_v1.0.1_Setup.exe)
- **macOS:** [RpiM_Studio_Beta_v1.0.1_macOS.dmg](https://github.com/Wyzuee/RpiM-Studio/releases/download/V1.0.1/RpiM_Studio_Beta_v1.0.1_macOS.dmg)

[Tüm Releases sürümlerini görüntüle](https://github.com/Wyzuee/RpiM-Studio/releases)

> Bu depo yalnızca yayın, kurulum ve güncelleme sayfasıdır. Kaynak kodu ve proje arşivleri yayımlanmaz; yalnızca Windows EXE ve macOS DMG dağıtılır.

## Kurulum

### Windows

1. Releases sayfasından `RpiM_Studio_Beta_v1.0.1_Setup.exe` dosyasını indirin.
2. Dosyayı çalıştırın ve kurulum sihirbazını tamamlayın.
3. RπM Studio'yu açın, hesabınıza giriş yapın ve TikTok yayıncı adınızı kontrol edin.

### macOS

1. Releases sayfasından `RpiM_Studio_Beta_v1.0.1_macOS.dmg` dosyasını indirin.
2. DMG'yi açıp **RπM Studio.app** uygulamasını Applications klasörüne sürükleyin.
3. İlk açılışta macOS güvenlik uyarısı gösterirse Sistem Ayarları → Gizlilik ve Güvenlik bölümünden uygulamayı onaylayın.

## Euler API kurulumu

1. Uygulamada **Ayarlar → Bağlantı** bölümünü açın.
2. **Euler hesabı aç** düğmesiyle EulerStream hesabı oluşturun veya mevcut hesabınıza giriş yapın.
3. EulerStream panelinden API anahtarınızı alın.
4. Anahtarı uygulamadaki **Euler API Key** alanına yapıştırıp kaydedin.
5. Ana ekranda **TikTok LIVE'a bağlan** düğmesine basın.

API anahtarı yalnızca cihazınızda saklanır; GitHub'a gönderilmez.

## Güncellemeler

Uygulama açılışta GitHub Releases alanını kontrol eder. **Ayarlar → Güncelleme** bölümünden de manuel kontrol başlatabilirsiniz. Yeni sürüm bulunduğunda uygulama önce sorar:

- **Güncelle ve Yükle:** işletim sisteminize uygun paketi indirir ve kurulumu başlatır.
- **Şimdi Değil:** güncellemeyi erteleyip uygulamayı açık bırakır.

Güncelleme dosyaları platforma göre seçilir; Windows uygulaması yalnızca EXE, macOS uygulaması yalnızca DMG arar. Yeni sürümler Beta v1.0.2, Beta v1.0.3 şeklinde devam eder.

Dosya adlandırma kuralı:

- Windows: `RpiM_Studio_Beta_vX.Y.Z_Setup.exe`
- macOS: `RpiM_Studio_Beta_vX.Y.Z_macOS.dmg`

Windows ve macOS paketleri aynı Release altında veya ayrı Releases altında yayımlanabilir. Uygulama kendi işletim sistemine uygun en yeni paketi seçer.
