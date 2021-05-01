#!/bin/bash

# where to connect to. I have my ssh config setup so this works
# more normal would be pi@192.168.0.???
# make sure the user is member of the wireshark group or add `sudo ` before `tshark`
raspi=raspi

ssh $raspi 'tshark -i bluetooth0 -w -' | wireshark -k -i -
