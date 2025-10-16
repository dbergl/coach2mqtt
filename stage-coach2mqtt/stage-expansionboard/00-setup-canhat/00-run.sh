#!/bin/bash -e

# Clear any existing config from previous stage
sed '/^\[all\]/q' -i -- "${ROOTFS_DIR}/boot/firmware/config.txt"

# Update config.txt for Waveshare Isolated RS232 / RS485 / CAN / CAN FD Expansion Board
# https://www.waveshare.com/product/raspberry-pi/hats/interface-power/rs232-rs485-can-board.htm
sed '/^\[all\]/r'<(cat <<EOF
dtoverlay=i2c0
dtoverlay=spi1-3cs
dtoverlay=sc16is752-spi1,int_pin=25
dtoverlay=mcp2515,spi0-0,oscillator=16000000,interrupt=23
dtoverlay=mcp251xfd,spi0-1,interrupt=24
EOF
) -i -- "${ROOTFS_DIR}/boot/firmware/config.txt"

#can0 and can1 configuration for systemd-networkd
install -v -m 644 files/80-can.link "${ROOTFS_DIR}/etc/systemd/network/"
install -v -m 644 files/81-can.link "${ROOTFS_DIR}/etc/systemd/network/"

# Override MODBUS RTU environment variable to point to RS485_1
if [ ! -d "${ROOTFS_DIR}/opt/coach2mqtt/.env" ] ; then
    cp "${ROOTFS_DIR}/opt/coach2mqtt/.env.example" \
    "${ROOTFS_DIR}/opt/coach2mqtt/.env" 
fi
echo "RTU=/dev/ttySC0" >> "${ROOTFS_DIR}/opt/coach2mqtt/.env"

on_chroot << EOF
# Enable serial hardware
/usr/bin/raspi-config nonint do_serial_hw 0
# Disable Serial console
/usr/bin/raspi-config nonint do_serial_cons 1
EOF

