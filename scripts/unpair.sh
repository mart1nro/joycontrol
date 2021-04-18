#!/bin/bash

# unpairs the switch to allow for repairing

switch_mac=$(bluetoothctl paired-devices | grep -F "Nintendo Switch" | grep -oE "([0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}")

if [ ! -z "$switch_mac" ]; then
	bluetoothctl remove $switch_mac
else
	echo "no switch found"
fi

