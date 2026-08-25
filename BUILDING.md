# RπM Studio v53 – Build

## Windows
`BUILD_RELEASE.bat` çalıştırın.

Çıktı: `installer_output/RpiM_Studio_Setup_v53.exe`

Builder Python sanal ortamını, bağımlılıkları, PyInstaller paketini ve gerekirse Inno Setup'ı hazırlar.

## macOS
Terminalde veya Finder'dan `BUILD_RELEASE.command` çalıştırın. İlk çalıştırmada macOS dosyanın çalıştırılmasına izin vermenizi isteyebilir.

Çıktı: `release_output/RpiM_Studio_v53_macOS.dmg`

Builder PyInstaller ile `.app` üretir, ardından macOS'un `hdiutil` aracıyla DMG oluşturur.

## Önemli
Windows EXE/Setup Windows üzerinde, macOS DMG macOS üzerinde derlenmelidir. PyInstaller cross-compile yapmaz; aynı kaynak kodu ve aynı builder işletim sistemini otomatik algılar.
