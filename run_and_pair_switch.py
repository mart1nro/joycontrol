import asyncio
import logging
import os
import socket

import logging_default as log
import utils
from controller_state import ButtonState, ControllerState
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

    protocol = protocol_factory()

    hid = HidDevice()
    # setting bluetooth adapter name and class to the device we wish to emulate
    await hid.set_name(protocol.controller.device_name())
    await hid.set_class()

    logger.info('Advertising the Bluetooth SDP record...')
    hid.register_sdp_record('profile/sdp_record_hid_pro.xml')
    hid.discoverable()

    loop = asyncio.get_event_loop()
    client_ctl, ctl_address = await loop.sock_accept(ctl_sock)
    logger.info(f'Accepted connection at psm {ctl_psm} from {ctl_address}')
    client_itr, itr_address = await loop.sock_accept(itr_sock)
    logger.info(f'Accepted connection at psm {itr_psm} from {itr_address}')
    assert ctl_address[0] == itr_address[0]

    transport = L2CAP_Transport(asyncio.get_event_loop(), protocol, client_itr, 50)
    protocol.connection_made(transport)

    return transport, protocol


async def send_empty_input_reports(transport):
    report = InputReport()

    while True:
        await transport.write(report)
        await asyncio.sleep(1)


async def button_push(controller_state, button, sec=0.1):
    button_state = ButtonState()

    # push button
    getattr(button_state, button)()

    # send report
    controller_state.set_button_state(button_state)
    await controller_state.send()
    await asyncio.sleep(sec)

    # release button
    getattr(button_state, button)()

    # send report
    controller_state.set_button_state(button_state)
    await controller_state.send()


async def test_controller_buttons(controller_state: ControllerState):
    """
    Goes to the "Test Controller Buttons" menu and presses all buttons
    """
    await controller_state.connect()

    # We assume we are in the "Change Grip/Order" menu of the switch
    await button_push(controller_state, 'home')

    # wait for the animation
    await asyncio.sleep(1)

    # Goto settings
    await button_push(controller_state, 'down')
    await asyncio.sleep(0.3)
    for _ in range(4):
        await button_push(controller_state, 'right')
        await asyncio.sleep(0.3)
    await button_push(controller_state, 'a')
    await asyncio.sleep(0.3)

    # go all the way down
    await button_push(controller_state, 'down', sec=3)
    await asyncio.sleep(0.3)

    # goto "Controllers and Sensors" menu
    for _ in range(2):
        await button_push(controller_state, 'up')
        await asyncio.sleep(0.3)
    await button_push(controller_state, 'right')
    await asyncio.sleep(0.3)

    # go all the way down
    await button_push(controller_state, 'down', sec=3)
    await asyncio.sleep(0.3)

    # goto "Test Input Devices" menu
    await button_push(controller_state, 'up')
    await asyncio.sleep(0.3)
    await button_push(controller_state, 'a')
    await asyncio.sleep(0.3)

    # goto "Test Controller Buttons" menu
    await button_push(controller_state, 'a')
    await asyncio.sleep(0.3)

    # push all buttons
    button_list = ['y', 'x', 'b', 'a', 'r', 'zr',
                   'minus', 'plus', 'r_stick', 'l_stick',
                   'down', 'up', 'right', 'left', 'l', 'zl']
    for i in range(10):
        for button in button_list:
            await button_push(controller_state, button)
            await asyncio.sleep(0.1)


async def main():
    transport, protocol = await create_hid_server(controller_protocol_factory(Controller.PRO_CONTROLLER), 17, 19)

    # send some empty input reports until the switch decides to reply
    future = asyncio.ensure_future(send_empty_input_reports(transport))
    await protocol.wait_for_output_report()
    future.cancel()
    try:
        await future
    except asyncio.CancelledError:
        pass

    await test_controller_buttons(ControllerState(transport, protocol))

    logger.info('Stopping communication...')
    await transport.close()


if __name__ == '__main__':
    # check if root
    if not os.geteuid() == 0:
        raise PermissionError('Script must be run as root!')

    # setup logging
    log.configure()

    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
