#!/bin/bash -e

if [ -d "${ROOTFS_DIR}/opt/coach2mqtt" ] ; then
    rm -rf "${ROOTFS_DIR}/opt/coach2mqtt"
fi

git clone --depth=1 --single-branch --branch main \
    https://github.com/dbergl/coach2mqtt.git "${ROOTFS_DIR}/opt/coach2mqtt"

chown -R 1000:1000 "${ROOTFS_DIR}/opt/coach2mqtt"

cp "${ROOTFS_DIR}/opt/coach2mqtt/configs/mosquitto/mosquitto.conf.example" \
    "${ROOTFS_DIR}/opt/coach2mqtt/configs/mosquitto/mosquitto.conf"

#Use systemd to start service
install -m 644 files/coach2mqtt.service "${ROOTFS_DIR}/lib/systemd/system/"

#Install .bash_aliases
install -m 644 files/bash_aliases "${ROOTFS_DIR}/home/${FIRST_USER_NAME}/.bash_aliases

on_chroot << EOF
systemctl enable coach2mqtt.service
ln -s /opt/coach2mqtt /home/${FIRST_USER_NAME}/coach2mqtt 
EOF
