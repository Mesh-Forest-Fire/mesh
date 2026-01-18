#!/bin/bash
set -e

echo "[*] Switching to MESH (ad-hoc) mode"

sudo systemctl stop wpa_supplicant
sudo systemctl stop NetworkManager 2>/dev/null || true
sudo systemctl stop dhcpcd

sudo ip link set wlan0 down

sudo iwconfig wlan0 mode ad-hoc
sudo iwconfig wlan0 essid forestmesh
sudo iwconfig wlan0 channel 1

sudo ip link set wlan0 up

sudo ip addr flush dev wlan0
# We change the .2 to .1, .2, .3 etc. for different nodes
sudo ip addr add 10.0.0.2/24 broadcast 10.0.0.255 dev wlan0

echo "[*] Mesh mode active. You can now run your mesh script."