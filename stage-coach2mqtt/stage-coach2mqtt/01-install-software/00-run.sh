#!/bin/bash -e

#Docker repo
install -m 644 files/docker.asc "${ROOTFS_DIR}/etc/apt/keyrings/"
install -m 644 files/docker.list "${ROOTFS_DIR}/etc/apt/sources.list.d/"
sed -i "s/RELEASE/${RELEASE}/g" "${ROOTFS_DIR}/etc/apt/sources.list.d/docker.list"
sed -i "s/ARCH/arm64/g" "${ROOTFS_DIR}/etc/apt/sources.list.d/docker.list"

#AllStarLink repo for cockpit wifi plugin
install -m 644 files/allstarlink.asc "${ROOTFS_DIR}/etc/apt/keyrings/"
install -m 644 files/allstarlink.list "${ROOTFS_DIR}/etc/apt/sources.list.d/"
sed -i "s/RELEASE/${RELEASE}/g" "${ROOTFS_DIR}/etc/apt/sources.list.d/allstarlink.list"

on_chroot <<- EOF
	ARCH="$(dpkg --print-architecture)"
    sed -i "s/ARCH/${ARCH}/g" "/etc/apt/sources.list.d/docker.list"
    sed -i "s/ARCH/${ARCH}/g" "/etc/apt/sources.list.d/allstarlink.list"

	apt-get update
EOF

