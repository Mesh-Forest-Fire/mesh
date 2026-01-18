#!/bin/bash
set -e

echo "[*] Switching to INTERNET mode"

# Bring interface down
sudo ip link set wlan0 down

# Restore managed mode
sudo iwconfig wlan0 mode managed

# Restart network services
sudo systemctl start wpa_supplicant
sudo systemctl start dhcpcd
sudo systemctl start NetworkManager 2>/dev/null || true

# Bring interface up
sudo ip link set wlan0 up

echo "[*] Now connect to WiFi using raspi-config or nmcli"
