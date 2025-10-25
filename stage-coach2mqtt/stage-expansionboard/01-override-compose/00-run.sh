#!/bin/bash -e

# Add docker-compose.override.yml
# This overrides and adds configuration to use the expansion board rs485 interface
install -v -m 644 -o ${FIRST_USER_NAME} -g ${FIRST_USER_NAME} files/docker-compose.override.yml ""${ROOTFS_DIR}/opt/coach2mqtt/
