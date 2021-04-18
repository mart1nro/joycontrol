#!/bin/bash

# where to connect to. I have my ssh config setup so this works
# more normal would be pi@192.168.0.???
raspi=raspi

mkfifo /tmp/shark.pcapng
ssh $raspi 'tshark -i bluetooth0 -w -" > /tmp/shark.pcapng
wireshark -k -i /tmp/shark.pcapng &

