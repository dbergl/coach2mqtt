#!/bin/bash -e

# Disable DUMP_OBSS from /sys/kernel/debug/ieee80211/phy0/features to get rid of error in logs
# and possible wifi instability

install -v -m 644 files/brcmfmac.conf "${ROOTFS_DIR}/etc/modprobe.d/"
