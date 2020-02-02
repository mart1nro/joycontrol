import asyncio
import logging
import socket

import pkg_resources

from joycontrol import utils
from joycontrol.device import HidDevice
from joycontrol.report import InputReport
from joycontrol.transport import L2CAP_Transport

PROFILE_PATH = pkg_resources.resource_filename('joycontrol', 'profile/sdp_record_hid.xml')
logger = logging.getLogger(__name__)


async def _send_empty_input_reports(transport):
    report = InputReport()

    while True:
        await transport.write(report)
        await asyncio.sleep(1)


async def create_hid_server(protocol_factory, ctl_psm, itr_psm):
    ctl_sock = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_SEQPACKET, socket.BTPROTO_L2CAP)
    itr_sock = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_SEQPACKET, socket.BTPROTO_L2CAP)

    # for some reason we need to restart bluetooth here, the Switch does not connect to the sockets if we don't...
    logger.info('Restarting bluetooth service...')
    await utils.run_system_command('systemctl restart bluetooth.service')
    await asyncio.sleep(1)

    ctl_sock.setblocking(False)
    itr_sock.setblocking(False)

    ctl_sock.bind((socket.BDADDR_ANY, ctl_psm))
    itr_sock.bind((socket.BDADDR_ANY, itr_psm))

    ctl_sock.listen(1)
    itr_sock.listen(1)

    protocol = protocol_factory()

    hid = HidDevice()
    # setting bluetooth adapter name and class to the device we wish to emulate
    await hid.set_name(protocol.controller.device_name())
    await hid.set_class()

    logger.info('Advertising the Bluetooth SDP record...')
    hid.register_sdp_record(PROFILE_PATH)
    hid.discoverable()

    loop = asyncio.get_event_loop()
    client_ctl, ctl_address = await loop.sock_accept(ctl_sock)
    logger.info(f'Accepted connection at psm {ctl_psm} from {ctl_address}')
    client_itr, itr_address = await loop.sock_accept(itr_sock)
    logger.info(f'Accepted connection at psm {itr_psm} from {itr_address}')
    assert ctl_address[0] == itr_address[0]

    transport = L2CAP_Transport(asyncio.get_event_loop(), protocol, client_itr, 50)
    protocol.connection_made(transport)

    # send some empty input reports until the switch decides to reply
    future = asyncio.ensure_future(_send_empty_input_reports(transport))
    await protocol.wait_for_output_report()
    future.cancel()
    try:
        await future
    except asyncio.CancelledError:
        pass

    return transport, protocol
