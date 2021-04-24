#!/bin/bash

# where to connect to. I have my ssh config setup so this works
# more normal would be pi@192.168.0.???
raspi=raspi

ssh $raspi 'sudo tshark -i bluetooth0 -w -' | wireshark -k -i -
