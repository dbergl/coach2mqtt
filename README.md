# coach2mqtt
A project to send data to an MQTT broker from a Renogy battery BMS, the RV-C network, and a Renogy Inverter using MODBUS. It allows allows control of those devices from MQTT topics.

This project is heavily inspired by [eRVin](https://myervin.com/) and [CoachProxyOS](https://github.com/linuxkidd/coachproxy-os).

With the correct configuration files this should work with Jayco Swift Li, Entegra Ethos Li, Jayco Terrain, and Entegra Launch RVs.

## Software
To get the information to/from the RV-C bus, Renogy canbus, and Renogy MODBUS this project combines these projects:
* [can2mqtt](https://github.com/dbergl/can2mqtt) forked from [can2mqtt](https://github.com/jgeisler0303/can2mqtt)
* [rvc2mqtt](https://github.com/dbergl/rvc2mqtt) forked from [rvc2mqtt](https://github.com/spbrogan/rvc2mqtt)
* [modbus2mqtt](https://github.com/dbergl/modbus2mqtt) forked from [spicierModbus2mqtt](https://github.com/mbs38/spicierModbus2mqtt)
* [Mosquitto](https://mosquitto.org/) as the MQTT broker
* [NodeRed](https://nodered.org/) for automation

All run as [docker](https://www.docker.com/) containers locally on the Raspberry Pi.

To view and interact with RV systems on my phone I am using the [IoT MQTT Panel](https://blog.snrlab.in/iot/iot-mqtt-panel-user-guide/) app which is available for apple and android devices

## Setup
Documentation for running this project can be found [here](https://dbergl.github.io/coach2mqtt/#).
