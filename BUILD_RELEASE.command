#!/bin/bash
set -e
cd "$(dirname "$0")"
python3 BUILD_RELEASE.py
echo
read -n 1 -s -r -p "Tamamlandi. Kapatmak icin bir tusa basin..."
echo
