#!/bin/bash

# changes the vendor part (first 3 bytes) of the Mac address on a raspi 4B (tested)
# and 3B+ (untestd) to 94:58:CB for Nintendo Co. Ltd.

# For some reason after a reboot you have to run
# sudo hcitool cmd 0x3f 0x001 0x66 0x55 0x44 0x33 0x22 0x11
# where 11:22:33:44:55:66 is your mac address.
# (yes the ordering is on purpose, pass in reverse to hcitool)

if [ -z "$1" ]
then
	bdaddr_dev=$(bluetoothctl show | grep -Eo '(:[0-9a-fA-F]{2}){3}\s')
	target_addr="94:58:CB${bdaddr_dev}"
	echo "detected dev id: ${bdaddr_dev}"
else
	target_addr=$1
fi

echo "changing address to ${target_addr}"
bdaddr -i hci0 "${target_addr}"
hciconfig hci0 reset
systemctl restart bluetooth.service

echo "success"
