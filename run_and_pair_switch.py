import asyncio
import logging
import socket

import logging_default as log
import utils
from device import HidDevice
from protocol import controller_protocol_factory, Controller
from report import InputReport
from transport import L2CAP_Transport

logger = logging.getLogger(__name__)


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

    hid = HidDevice()
    # setting bluetooth adapter name and class to the device we wish to emulate
    await hid.set_name(HidDevice.JOYCON_L)
    await hid.set_class()

    logger.info('Advertising the Bluetooth SDP record...')
    hid.register_sdp_record('profile/sdp_record_hid_pro.xml')
    hid.discoverable()

    loop = asyncio.get_event_loop()
    client_ctl, address = await loop.sock_accept(ctl_sock)
    logger.info(f'Accepted connection at psm {ctl_psm} from {address}')
    client_itr, address = await loop.sock_accept(itr_sock)
    logger.info(f'Accepted connection at psm {itr_psm} from {address}')

    protocol = protocol_factory()
    transport = L2CAP_Transport(asyncio.get_event_loop(), protocol, client_itr, address, 50)
    protocol.connection_made(transport)

    return transport, protocol


async def send_empty_input_reports(transport):
    report = InputReport()

    while True:
        await transport.write(bytes(report))
        await asyncio.sleep(1)


async def main():
    transport, protocol = await create_hid_server(controller_protocol_factory(Controller.JOYCON_L), 17, 19)

    future = asyncio.ensure_future(send_empty_input_reports(transport))

    await protocol.wait_for_output_report()

    future.cancel()
    try:
        await future
    except asyncio.CancelledError:
        pass

    await transport.close()


if __name__ == '__main__':
    # setup logging
    log.configure()

    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())