#!/bin/bash

# changes the vendor part (first 3 bytes) of the Mac address on a raspi 4B (tested)
# and 3B+ (untestd) to 94:58:CB for Nintendo Co. Ltd.

bdaddr_dev=$(bluetoothctl show | grep -Eo '(:[0-9a-fA-F]{2}){3}\s')

echo "detected dev id: ${bdaddr_dev}, changing address to 94:58:CB${bdaddr_dev}"

bdaddr -i hci0 "94:58:CB${bdaddr_dev}"
hciconfig hci0 reset
systemctl restart bluetooth.service

echo "success"
