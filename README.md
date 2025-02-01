# coach2mqtt
A project to send data to an MQTT broker from both the Renogy battery BMS and and the RV-C network.

Based off of [can2mqtt](https://github.com/jgeisler0303/can2mqtt) and [rvc2mqtt](https://github.com/spbrogan/rvc2mqtt)

With the correct configuration files this should work with Jayco Swift Li, Entegra Ethos Li, Jayco Terrain, and Entegra Launch RVs

## Hardware needed:
* [Rasperry Pi 4b](https://www.raspberrypi.com/products/raspberry-pi-4-model-b/)
   This can likely run on much lower powered devices but it is currently being developed and tested on a Raspberry Pi 4b.
   You will also need a microSD card to hold the OS and software files.

* [Dual Can Hat with SMPS](https://copperhilltech.com/pican2-duo-can-bus-board-for-raspberry-pi-4-with-3a-smps/)
   I recommend the canhat with SMPS so you can power the Pi off the RV-C bus

* [3m mini plug connector](https://www.fireflyint.com/products/70090-3m-mini-plug-connector)
   This plug will allow you to connect to the RV-C bus in your coach

* [RV-C drop cable](https://www.fireflyint.com/products/70053-24ga-rv-c-drop-cable)
   Order enough cable that you can locate the Rasperry Pi in a location where it will be safe and can get a good signal to your wifi router, but it should be less than 6ft as recommended by the RV-C standard. You can also make a cable out of ethernet cable, for example.

* [Renogy debug port connector](https://www.amazon.com/dp/B0BX42NJWR)
   This connector is needed to connect to your Renogy battery debug port. Alternatively you could tap into the canbus wires going to the APS-500.

* A wifi network your Raspberry Pi and phone can connect to. In order to be able to remotely monitor and control your device the wifi network you connect to must also connect to the internet.

## Software
To get the information from both the RV-C bus and the Renogy canbus this project combines 3 projects:
* [can2mqtt](https://github.com/dbergl/can2mqtt)
* [rvc2mqtt](https://github.com/dbergl/rvc2mqtt)
* [Mosquitto](https://mosquitto.org/)

All 3 run as [docker](https://www.docker.com/) containers locally on the Raspberry Pi.

To view and interact with RV systems on my phone I am using the [IoT MQTT Panel](https://blog.snrlab.in/iot/iot-mqtt-panel-user-guide/) app which is available for apple and android devices

## Software setup
Eventually I hope to make a custom image but for now these are the steps to get started.

1. Install your choice of OS on the Raspberry Pi using the [official imager tool](https://www.raspberrypi.com/software/)
   I recommend installing The latest Raspberry Pi OS Lite (64 bit) - Currently this is Debian Bookworm

   It is easiest to set up your wifi and login username/password using the advanced settings of the imager tool

2. Start your pi up and connect to it over the network you configured or locally connected to a monitor and keyboard.

3. Enable the Can Hat
   If you are using the PiCan Duo and debian bookworm you can enable it by editing `/boot/firmware/config.txt`:
Uncomment `#dtparam=spi=on` by changing it to `dtparam=spi=on`

   Add:

       dtoverlay=mcp2515-can0,oscillator=16000000,interrupt=25
       dtoverlay=mcp2515-can1,oscillator=16000000,interrupt=24

   to the end of the file in the `[all]` section
4. Set can to autostart on boot:
   * Create the file `/etc/modules-load.d/can.conf` and add these lines:
    ```bash
       can
       can_raw
    ```
   * Create the file `/etc/network/interfaces.d/can0` and add these lines:
    ```bash
    auto can0
    iface can0 inet manual
      pre-up /sbin/ip link set can0 txqueuelen 100 type can bitrate 250000 restart-ms 100
      up /sbin/ifconfig can0 up
      down /sbin/ifconfig can0 down
    ```
   * Create the file `/etc/network/interfaces.d/can1` and add these lines:
    ```bash
    auto can1
    iface can1 inet manual
      pre-up /sbin/ip link set can1 txqueuelen 100 type can bitrate 250000 restart-ms 100
      up /sbin/ifconfig can1 up
      down /sbin/ifconfig can1 down
    ```

5. Install docker
   - Instructions can be found [here](https://docs.docker.com/engine/install/debian/#install-using-the-repository).
   - Post install instructions [here](https://docs.docker.com/engine/install/linux-postinstall/).

6. Update packages and install a few programs
   ```bash
   sudo apt update
   sudo apt upgrade
   sudo apt install -y git can-utils
   ```

7. Clone this repo:
   ```bash
   cd ~ && git clone https://github.com/dbergl/coach2mqtt
   ```

8. Make a copy of the example config files and modify as desired/needed
   ```bash
   cd ~/coach2mqtt/configs
   cp mosquitto/mosquitto.conf.example mosquitto/mosquitto.conf
   # Optionally copy the logger config too
   cp rvc2mqtt/rvc_logger.yml.example rvc2mqtt/rvc_logger.yml
   ```

   - `can2mqtt/config.json` holds the configuration for communication with the Renogy battery BMS
   - `mosquitto/mosquitto.conf` holds the configuration for the MQTT server. Your phone app will communicate with this.
   - `rvc2mqtt/rvc_logger.yml` is optional and contains settings for logging RV-C messages to a file.

9. Make a copy of the .env file and edit to suit your needs
   ```bash
   cd ~/coach2mqtt/
   cp .env.example .env
   ```

   - .env sets certain environment variables that are used by the docker containers
      - `RVC_CAN_INTERFACE_NAME` sets the can device connected to the RV-C bus. Defaults to `can0` if not set
      - `RVC_FLOORPLAN_FILE` sets filename of the floorplan file for your coach. floorplan files are in configs/rvc2mqtt/
      - `RVC_LOG_CONFIG_FILE` sets the name of the RV-C logger config file. Set this if you want to tail the RV-C bus logs
      - `CANBUS_CAN_INTERFACE_NAME` sets the can device connected to the Renogy bus. Defaults to `can1` if not set
      - `CANBUS_CONFIG_FILE` Similar to the floorplan file but used to config the Renogy bus listener. Defaults to `config.json` if not set
      - `MQTT_HOST` Sets host/domain name of the MQTT broker. Defaults to `localhost` if not set
      - `MQTT_PORT` Sets MQTT port to use when connecting to MQTT broker. Defaults to `1883` if not set

## Starting the services

- Start the containers
  ```bash
  cd ~/coach2mqtt
  docker compose up -d
  ```

At this point the containers should start up and should begin publishing messages to the MQTT broker.

-  Verify containers are running
   ```bash
   docker ps
   ```
  
   You should see your three containers running: 
   - coach2mqtt-rvc2mqtt-1
   - coach2mqtt-can2mqtt-1
   - coach2mqtt-mosquitto-1


