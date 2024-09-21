!#/bin/bash

sudo apt update && \
    sudo apt upgrade -y && \
    sudo apt install -y can-utils git

cd ~

git clone https://github.com/dbergl/coach2mqtt.git

cd coach2mqtt

mkdir logs config floorplan

echo "Starting the containers"
docker compose up -d




