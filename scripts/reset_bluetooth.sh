#!/bin/bash

# To modify bluetooth settings: /lib/systemd/system/bluetooth.service


# remove any device specific configurations, logs, etc...
rm -r /var/lib/bluetooth

# just to be sure redownload bluez
#apt --reinstall install bluez

# reset all configurations and rewrite device specific setup
dpkg-reconfigure bluez

./restart_bluetooth.sh

# do that again, because sometime it doesn't work
sleep 3

./restart_bluetooth.sh
