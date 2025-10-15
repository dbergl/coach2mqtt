#!/bin/bash -e

if [ "${WAVESHARESKU}" == "27338" ]; then
    # Update config.txt for Waveshare 2-Ch Can Hat+
    # https://www.waveshare.com/wiki/2-CH_CAN_HAT+
    sed '/^\[all\]/r'<(cat <<EOF
    dtoverlay=spi1-3cs
    dtoverlay=mcp2515,spi1-1,oscillator=16000000,interrupt=22
    dtoverlay=mcp2515,spi1-2,oscillator=16000000,interrupt=13
    EOF
    ) -i -- "${ROOTFS_DIR}/boot/firmware/config.txt"
elif [ "${WAVESHARESKU}" == "28164" ]; then
    # Update config.txt for Waveshare Isolated RS232 / RS485 / CAN / CAN FD Expansion Board
    # https://www.waveshare.com/product/raspberry-pi/hats/interface-power/rs232-rs485-can-board.htm
    sed '/^\[all\]/r'<(cat <<EOF
    dtoverlay=spi1-3cs
    dtoverlay=mcp2515,spi1-1,oscillator=16000000,interrupt=22
    dtoverlay=mcp2515,spi1-2,oscillator=16000000,interrupt=13
    EOF
    ) -i -- "${ROOTFS_DIR}/boot/firmware/config.txt"
fi

#Enable can modules
install -v -m 644 files/can.conf "${ROOTFS_DIR}/etc/modules-load.d/can.conf"

#can0 and can1 configuration for systemd-networkd
install -v -m 644 files/80-can.link "${ROOTFS_DIR}/etc/systemd/network/"
install -v -m 644 files/81-can.link "${ROOTFS_DIR}/etc/systemd/network/"
install -v -m 644 files/80-can.network "${ROOTFS_DIR}/etc/systemd/network/"

#networkd should only wait for the can links
install -v -m 755 -d "${ROOTFS_DIR}/etc/systemd/system/systemd-networkd-wait-online.service.d"
install -v -m 644 files/override.conf "${ROOTFS_DIR}/etc/systemd/system/systemd-networkd-wait-online.service.d/"

on_chroot << EOF
systemctl enable systemd-networkd
EOF

