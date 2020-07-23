import argparse
import asyncio
import logging
import os
import socket
import struct
import time

import hid

from joycontrol import logging_default as log, utils
from joycontrol.device import HidDevice
from joycontrol.server import PROFILE_PATH
from joycontrol.utils import AsyncHID

logger = logging.getLogger(__name__)

VENDOR_ID = 1406
PRODUCT_ID_JL = 8198
PRODUCT_ID_JR = 8199
PRODUCT_ID_PC = 8201


class Relay:
    def __init__(self, capture_file=None):
        self._capture_file = capture_file

    async def relay_input(self, hid_device, client_itr):
        loop = asyncio.get_event_loop()

        while True:
            data = await hid_device.read(100)
            # add adding byte for input report
            data = b'\xa1' + data

            if self._capture_file is not None:
                # write data to log file
                current_time = struct.pack('d', time.time())
                size = struct.pack('i', len(data))
                self._capture_file.write(current_time + size + data)

            await loop.sock_sendall(client_itr, data)
            await asyncio.sleep(0)

    async def relay_output(self, hid_device, client_itr):
        loop = asyncio.get_event_loop()

        while True:
            data = await loop.sock_recv(client_itr, 50)

            if self._capture_file is not None:
                # write data to log file
                current_time = struct.pack('d', time.time())
                size = struct.pack('i', len(data))
                self._capture_file.write(current_time + size + data)

            # remove padding byte for output report (not required when using the hid driver)
            data = data[1:]

            await hid_device.write(data)
            await asyncio.sleep(0)


async def get_hid_controller():
    logger.info('Waiting for HID devices... Please connect JoyCon over bluetooth. '
                'Note: The bluez "input" plugin needs to be enabled (default)"')

    controller = None

    while controller is None:
        for device in hid.enumerate(0, 0):
            # looking for devices matching Nintendo's vendor id and JoyCon product id
            if device['vendor_id'] == VENDOR_ID and device['product_id'] in (PRODUCT_ID_JL, PRODUCT_ID_JR, PRODUCT_ID_PC):
                controller = device
                break
        else:
            await asyncio.sleep(2)

    logger.info(f'Found controller "{controller}".')

    return controller


async def _main(capture_file=None, reconnect_bt_addr=None):
    loop = asyncio.get_event_loop()

    if reconnect_bt_addr == None:
        # Creating l2cap sockets, we have to do this before restarting bluetooth
        ctl_sock = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_SEQPACKET, socket.BTPROTO_L2CAP)
        itr_sock = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_SEQPACKET, socket.BTPROTO_L2CAP)

        # HACK: To circumvent incompatibilities with the bluetooth "input" plugin, we need to restart Bluetooth here.
        # The Switch does not connect to the sockets if we don't.
        # For more info see: https://github.com/mart1nro/joycontrol/issues/8
        logger.info('Restarting bluetooth service...')
        await utils.run_system_command('systemctl restart bluetooth.service')
        await asyncio.sleep(1)

        controller = await get_hid_controller()

        logger.info('Connecting with the Switch... Please open the "Change Grip/Order" menu.')

        ctl_sock.setblocking(False)
        itr_sock.setblocking(False)

        ctl_sock.bind((socket.BDADDR_ANY, 17))
        itr_sock.bind((socket.BDADDR_ANY, 19))

        ctl_sock.listen(1)
        itr_sock.listen(1)

        emulated_hid = HidDevice()
        # setting bluetooth adapter name and class to the device we wish to emulate
        await emulated_hid.set_name(controller['product_string'])
        await emulated_hid.set_class()

        logger.info('Advertising the Bluetooth SDP record...')

        emulated_hid.register_sdp_record(PROFILE_PATH)
        #emulated_hid.powered(True)
        emulated_hid.discoverable(True)
        #emulated_hid.pairable(True)

        client_ctl, ctl_address = await loop.sock_accept(ctl_sock)
        logger.info(f'Accepted connection at psm 17 from {ctl_address}')
        client_itr, itr_address = await loop.sock_accept(itr_sock)
        logger.info(f'Accepted connection at psm 19 from {itr_address}')
        assert ctl_address[0] == itr_address[0]

        # stop advertising
        emulated_hid.discoverable(False)
    else:
        controller = await get_hid_controller()

        client_ctl = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_SEQPACKET, socket.BTPROTO_L2CAP)
        client_itr = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_SEQPACKET, socket.BTPROTO_L2CAP)

        client_ctl.connect((reconnect_bt_addr, 17))
        logger.info(f'Reconnected at psm 17 to switch {reconnect_bt_addr}')
        client_itr.connect((reconnect_bt_addr, 19))
        logger.info(f'Reconnected at psm 19 to switch {reconnect_bt_addr}')

        client_ctl.setblocking(False)
        client_itr.setblocking(False)

    relay = Relay(capture_file)

    logger.info('Relaying starting...')

    try:
        with AsyncHID(path=controller['path'], loop=loop) as hid_controller:
            await asyncio.gather(
                asyncio.ensure_future(relay.relay_input(hid_controller, client_itr)),
                asyncio.ensure_future(relay.relay_output(hid_controller, client_itr)),
            )
    finally:
        logger.info('Stopping communication...')
        client_itr.close()
        client_ctl.close()


if __name__ == '__main__':
    # check if root
    if not os.geteuid() == 0:
        raise PermissionError('Script must be run as root!')

    parser = argparse.ArgumentParser()
    parser.add_argument('-l', '--log', help='log file path for capturing communication')
    parser.add_argument('-r', '--reconnect_bt_addr', type=str, default=None,
                        help='The Switch console Bluetooth address, for reconnecting as an already paired controller')
    args = parser.parse_args()

    # setup logging
    log.configure()

    with utils.get_output(args.log, default=None) as capture_file:
        loop = asyncio.get_event_loop()
        loop.run_until_complete(
            _main(capture_file=capture_file, reconnect_bt_addr=args.reconnect_bt_addr)
        )

