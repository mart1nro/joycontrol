import argparse
import asyncio
import logging
import os
import socket
import re

import hid

from joycontrol import logging_default as log, utils
from joycontrol.device import HidDevice
from joycontrol.server import PROFILE_PATH
from joycontrol.utils import AsyncHID

logger = logging.getLogger(__name__)

async def recv_to_queue(queue, src, side):
    while True:
        data = await src()
        await queue.put(data)
        #try:
        #    queue.put_nowait(data)
        #except asyncio.QueueFull:
        #    print(side, "overrun")
        #    #queue.get_nowait()
        #    #queue.put_nowait(data)
        if queue.qsize() > 1:
            print(side, queue.qsize())

async def send_from_queue(queue, dst, printd=False):
    # @yamakaky I too would love to use python 3.8 but raspis ship with 3.7 :(
    while True:
        data = await queue.get()
        await dst(data)
        if printd:
            print("send")

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

class NoDatagramProtocol(asyncio.DatagramProtocol):
    """
    This is a gutted version of the protcol-transport paradigm in asyncio that
    has an api more similar to sockets. More perciseley the protocoll part.
    Neccessary because asyncio has no datagram socket support.

    @param peer: the address of the peer to "connect" to.
    """
    def __init__(self, peer):
        self.peer = peer
        self.connected = asyncio.Event()
        self.transport = None
        self.readQueue = asyncio.Queue(10)

    async def read(self):
        return await self.readQueue.get()

    async def write(self, data):
        await self.connected.wait()
        self.transport.sendto(data, self.peer)

    def datagram_received(self, data, addr):
        if self.peer == addr:
            try:
                self.readQueue.put_nowait(data)
            except:
                print("dropped packet")
        else:
            print("warning: unknown source, dropped")

    def connection_made(self, transport):
        self.transport = transport
        self.connected.set()

    def error_received(self, exc):
        print('Error received:', exc)

    def connection_lost(self, exc):
        self.connected.clear()
        self.transport = None


async def connectEth(eth, server=False):
    ip, port = eth.split(':')
    port = int(port)

    t, p = await asyncio.get_event_loop().create_datagram_endpoint(lambda: NoDatagramProtocol((ip, port)), local_addr=('0.0.0.0', port), remote_addr=(ip, port))

    # replaces the syn-ack handshake with just sending a single packet to test the
    # connection beforehand
    if server:
        await p.read()
    else:
        await p.write(bytes(10))

    return p.read, p.write, t.close

async def _main(sw_addr, jc_addr, buffer=10):
    # loop = asyncio.get_event_loop()

    jc_eth = not re.match("([0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}", jc_addr)
    sw_eth = not re.match("([0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}", sw_addr)

    sw_any = sw_addr == "00:00:00:00:00:00"

    print("jc_eth", jc_eth, "sw_eth", sw_eth)

    jc_queue = asyncio.Queue(buffer)
    sw_queue = asyncio.Queue(buffer)

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
            recv_from_jc, send_to_jc, cleanup_jc = await connectEth(jc_addr, True)

        if sw_eth:
            print("opening switch eth")
            recv_from_switch, send_to_switch, cleanup_switch = await connectEth(sw_addr, False)

        if not sw_eth:
            if not sw_any:
                print("waiting for switch")
                recv_from_switch, send_to_switch, cleanup_switch = bt_to_callbacks(*await connect_bt(sw_addr))
            else:
                recv_from_switch, send_to_switch, cleanup_switch = bt_to_callbacks(*await accept_bt())

        print("stared forwarding")
        await asyncio.gather(
            asyncio.ensure_future(recv_to_queue(jc_queue, recv_from_jc, ">")),
            asyncio.ensure_future(send_from_queue(jc_queue, send_to_switch)),
            asyncio.ensure_future(recv_to_queue(sw_queue, recv_from_switch, "<")),
            asyncio.ensure_future(send_from_queue(sw_queue, send_to_jc)),
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
    parser.add_argument('-B', '--buffer', type=int, default=10,
                        help='the buffersize to use for in and output.')

    args = parser.parse_args()
    if not args.switch or not args.joycon:
        print("missing args")
        exit(1)

    asyncio.run(_main(args.switch, args.joycon, buffer=args.buffer))
