#!/bin/python3

# because pyhton has no --include....
import sys
sys.path.insert(0, '..')

"""
joycon_ip_proxy.py

This is an improved fork of relay_joycon.py

In general this script forwards network traffic between two points. Those two
points beeing either Bluetooth-coonnections or TCP-Connections (or any combination)
The "Joycon (R)" part is hardcoded when using Bluetooth-connections, since:
- Joycon-L is rather unintresting
- I never could get Procon to work...

Options:
    -S, --switch <BT-addr or IP:Port combo>
        Where to talk to the switch. The script will try to connect to the given
        address and expects a server ready to accept the connection.
        Exception: when passing 00:00:00:00:00:00 it will instead open a Bluetooth-
        server and wait for the Switch to connect (using the change Grip/Order menu).
    -J, --joycon <BT-addr or IP:Port combo>
        Where to talk to the Joycon. THe script will wait (read: start a server)
        for a incoming connection from the given address and then attempt to
        connect to the switch.

How to use:
- Option A: Direct mode
    Assuming your switch is paired (meaning joycontrol -r would work) and
    has the MAC 94:58:CB:12:34:56, your Joycon has the MAC 94:58:CB:ab:cd:ef

    sudo joycon_ip_proxy.py -S 94:58:CB:12:34:56 -J 94:58:CB:ab:cd:ef

    If your switch is not paired, use

    sudo joycon_ip_proxy.py -S 00:00:00:00:00:00 -J 94:58:CB:ab:cd:ef

    then press the sync button on the joycon, wait for it to connect,
    then turn on the switch (and open the change grip menu in the second case).
    Then pray it works...

- Option B: Proxy via IP:
    Assuming same MACs as above, you have 2 machines with bluetooth adapters and
    both have port 33333 not used (you can use any other as you like),
    one at 192.168.0.100 intended to connect to the switch,
    the other at 192.168.0.101 intended to connect to the joycon.

    1. Make sure the ethernet connection has *no* packet drop, a low ping and is ideally >= 1Gbit

    2. on the first machine start the script like so:
    sudo joycon_ip_proxy.py -S 94:58:CB:12:34:56 -J 192.168.0.101:33333
    It should wait for the joycon now

    3. on the Second machine start the script like so:
    sudo joycon_ip_proxy.py -S 192.168.2.100:33333 -J 94:58:CB:ab:cd:ef
    It also should wait for the joycon

    4. press the Sync button on the joycon
    the second machine should report that it's now trying to connect to the switch,
    then the first should report the same and the second report that it already
    started forwarding

    5. Start the switch (and open the Change grip/order Menu if needed)
    the first macine should connect and then also report it started forwarding.

- Option C: yes you can supply IP addresses for both Switch AND Joycon,
    in that case just go download a Proxy or something... I thought we doing
    bluetooth debugging today.

Problems:
- The joycon just turns off: Most notably you were too slow.
- The switch axes the connection: It didn't feel like getting hacked today
- The Two machines in option B don't connect: see if you can `netcat` between
  given ports, maybe your firewall, etc... is blocking it.
- Port in use errors on subsequent runs: it takes 3-10 seconds to really "close"
  a TCP-port. Just wait.
"""



import argparse
import asyncio
import logging
import os
import socket
import re

# from yamakai

import hid

from joycontrol import logging_default as log, utils
from joycontrol.device import HidDevice
from joycontrol.server import PROFILE_PATH
from joycontrol.utils import AsyncHID

logger = logging.getLogger(__name__)

async def myPipe(src, dest):
    data = await src()
    while data:
        await dest(data)
        data = await src()

def read_from_sock(sock):
    async def internal():
        return await asyncio.get_event_loop().sock_recv(sock, 500)
    return internal

def write_to_sock(sock):
    async def internal(data):
        return await asyncio.get_event_loop().sock_sendall(sock, data)
    return internal

async def connect_bt(bt_addr):
    loop = asyncio.get_event_loop()
    ctl = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_SEQPACKET, socket.BTPROTO_L2CAP)
    itr = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_SEQPACKET, socket.BTPROTO_L2CAP)

    # See https://bugs.python.org/issue27929?@ok_message=issue%2027929%20versions%20edited%20ok&@template=item
    # bug here: https://github.com/python/cpython/blob/5e29021a5eb10baa9147fd977cab82fa3f652bf0/Lib/asyncio/selector_events.py#L495
    # should be
    # if hasattr(socket, 'AF_INET') or hasattr(socket, 'AF_INET6') sock.family in (socket.AF_INET, socket.AF_INET6):
    # or something similar
    # ctl.setblocking(0)
    # itr.setblocking(0)
    # await loop.sock_connect(ctl, (bt_addr, 17))
    # await loop.sock_connect(itr, (bt_addr, 19))
    ctl.connect((bt_addr, 17))
    itr.connect((bt_addr, 19))
    ctl.setblocking(0)
    itr.setblocking(0)
    return ctl, itr

async def accept_bt():
    loop = asyncio.get_event_loop()

    ctl_srv = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_SEQPACKET, socket.BTPROTO_L2CAP)
    itr_srv = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_SEQPACKET, socket.BTPROTO_L2CAP)

    print('Waitng for the Switch... Please open the "Change Grip/Order" menu.')

    ctl_srv.setblocking(False)
    itr_srv.setblocking(False)

    ctl_srv.bind((socket.BDADDR_ANY, 17))
    itr_srv.bind((socket.BDADDR_ANY, 19))

    ctl_srv.listen(1)
    itr_srv.listen(1)

    emulated_hid = HidDevice()
    # setting bluetooth adapter name and class to the device we wish to emulate
    await emulated_hid.set_name('Joy-Con (R)')
    logger.info('Advertising the Bluetooth SDP record...')
    emulated_hid.register_sdp_record(PROFILE_PATH)
    #emulated_hid.powered(True)
    emulated_hid.discoverable(True)
    #emulated_hid.pairable(True)
    await emulated_hid.set_class()

    ctl, ctl_address = await loop.sock_accept(ctl_srv)
    print(f'Accepted connection at psm 17 from {ctl_address}')
    itr, itr_address = await loop.sock_accept(itr_srv)
    print(f'Accepted connection at psm 19 from {itr_address}')
    assert ctl_address[0] == itr_address[0]

    # stop advertising
    emulated_hid.discoverable(False)
    ctl_srv.close()
    itr_srv.close()

    return ctl, itr

def bt_to_callbacks(ctl, itr):
    def internal():
        itr.close()
        ctl.close()
    return read_from_sock(itr), write_to_sock(itr), internal

async def connectEth(eth, server=False):
    loop = asyncio.get_event_loop()
    ip, port = eth.split(':')
    port = int(port)
    s = socket.socket()
    s.setblocking(0)
    if server:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(('0.0.0.0', port))
        s.listen(1)
        while 1:
            c, caddr = await loop.sock_accept(s)
            if caddr[0] == ip:
                s.close()
                c.setblocking(0)
                s = c
                break
            else:
                print("unexpecetd host", caddr)
                c.close()
    else:
        await loop.sock_connect(s, (ip, port))
    # make the data f****** go
    s.setsockopt(socket.SOL_TCP, socket.TCP_NODELAY, 1)
    return s

def eth_to_callbacks(sock):
    return read_from_sock(sock), write_to_sock(sock), lambda: sock.close()

async def _main(sw_addr, jc_addr):
    # loop = asyncio.get_event_loop()

    jc_eth = not re.match("([0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}", jc_addr)
    sw_eth = not re.match("([0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}", sw_addr)

    sw_any = sw_addr == "00:00:00:00:00:00"

    print("jc_eth", jc_eth, "sw_eth", sw_eth)

    send_to_jc = None
    recv_from_jc = None
    cleanup_jc = None

    send_to_switch = None
    recv_from_switch = None
    cleanup_switch = None
    try:
        # DONT do if-else here, because order should be easily adjustable
        if not jc_eth:
            print("waiting for joycon")
            recv_from_jc, send_to_jc, cleanup_jc = bt_to_callbacks(*await connect_bt(jc_addr))

        if jc_eth:
            print("opening joycon eth")
            recv_from_jc, send_to_jc, cleanup_jc = eth_to_callbacks(await connectEth(jc_addr, True))
            #print("waiting for initial packet")
            #print(await recv_from_jc())
            #print("got initial")

        if sw_eth:
            print("opening switch eth")
            recv_from_switch, send_to_switch, cleanup_switch = eth_to_callbacks(await connectEth(sw_addr, False))
            #print("waiting for initial packet")
            #print (await recv_from_switch())
            #print("got initial")

        if not sw_eth:
            if not sw_any:
                print("waiting for switch")
                recv_from_switch, send_to_switch, cleanup_switch = bt_to_callbacks(*await connect_bt(sw_addr))
            else:
                recv_from_switch, send_to_switch, cleanup_switch = bt_to_callbacks(*await accept_bt())

        print("stared forwarding")
        await asyncio.gather(
            asyncio.ensure_future(myPipe(recv_from_switch, send_to_jc)),
            asyncio.ensure_future(myPipe(recv_from_jc, send_to_switch)),
        )
    finally:
        if cleanup_switch:
            cleanup_switch()
        if cleanup_jc:
            cleanup_jc()



if __name__ == '__main__':
    # check if root
    if not os.geteuid() == 0:
        raise PermissionError('Script must be run as root!')

    parser = argparse.ArgumentParser(description="Acts as proxy for Switch-joycon communtcation between the two given addresses.\n Start the instance forwarding to the Switch directly first")
    parser.add_argument('-S', '--switch', type=str, default=None,
                        help='talk to switch at the given address. Either a BT-MAC or a tcp ip:port combo. 00:00:00:00:00:00 for pair mode.')
    parser.add_argument('-J', '--joycon', type=str, default=None,
                        help='talk to switch at the given address. Either a BT-MAC or a tcp ip:port combo.')

    args = parser.parse_args()
    if not args.switch or not args.joycon:
        print("missing args")
        exit(1)

    asyncio.run(_main(args.switch, args.joycon))
