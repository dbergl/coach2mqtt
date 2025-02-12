#!/bin/bash -e

usermod -a -G docker ${FIRST_USER_NAME}

ln -s /home/${FIRST_USER_NAME}/coach2mqtt /opt/coach2mqtt
