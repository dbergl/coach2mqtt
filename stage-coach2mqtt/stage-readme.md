Some notes about the custom pi-gen stage

config
  config file for pi-gen with defaults for this project

coach2mqtt
  custom build stage to add this project to a "lite" os build

What this stage does:

- Configures waveshare 2 channel can hat+ for autostart
  - enable systemd-networkd because networkmanager does not support canbus
  - override systemd-networkd-wait-online.service to only wait for can0 or can1 to be ready
- Installs and configures requirements for this project such as docker, cockpit, git
- Adds systemd service to autostart docker containers

