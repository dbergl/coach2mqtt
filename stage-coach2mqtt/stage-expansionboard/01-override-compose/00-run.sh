#!/bin/bash -e

# Add docker-compose.override.yml
# This overrides and adds configuration to use the expansion board rs485 interface
install -v -m 644 -o 1000 -g 1000 files/docker-compose.override.yml ""${ROOTFS_DIR}/opt/coach2mqtt/
