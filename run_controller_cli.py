import argparse
import asyncio
import logging
import os
import socket
from contextlib import contextmanager

from joycontrol import logging_default as log
from joycontrol.command_line_interface import ControllerCLI
from joycontrol.controller import Controller
from joycontrol.memory import FlashMemory
from joycontrol.protocol import controller_protocol_factory
from joycontrol.server import create_hid_server, create_reconnection
from joycontrol.report import InputReport

logger = logging.getLogger(__name__)


async def _main(controller, console_bt_addr=None, capture_file=None, spi_flash=None, device_id=None):
    factory = controller_protocol_factory(controller, spi_flash=spi_flash)
    ctl_psm, itr_psm = 17, 19
    if console_bt_addr is None:
        transport, protocol = await create_hid_server(factory, 
            ctl_psm=ctl_psm, itr_psm=itr_psm, capture_file=capture_file, device_id=device_id)
    else:
        transport, protocol = await create_reconnection(factory, 
            console_bt_addr,
            ctl_psm=ctl_psm, itr_psm=itr_psm, capture_file=capture_file)

    controller_state = protocol.get_controller_state()

    cli = ControllerCLI(controller_state)
    await cli.run()

    logger.info('Stopping communication...')
    await transport.close()


if __name__ == '__main__':
    # check if root
    if not os.geteuid() == 0:
        raise PermissionError('Script must be run as root!')

    # setup logging
    #log.configure(console_level=logging.ERROR)
    log.configure()

    parser = argparse.ArgumentParser()
    parser.add_argument('controller', help='JOYCON_R, JOYCON_L or PRO_CONTROLLER')
    parser.add_argument('-l', '--log')
    parser.add_argument('-d', '--device_id')
    parser.add_argument('--spi_flash')
    parser.add_argument('--console-bt-addr', type=str, default=None)
    args = parser.parse_args()

    if args.controller == 'JOYCON_R':
        controller = Controller.JOYCON_R
    elif args.controller == 'JOYCON_L':
        controller = Controller.JOYCON_L
    elif args.controller == 'PRO_CONTROLLER':
        controller = Controller.PRO_CONTROLLER
    else:
        raise ValueError(f'Unknown controller "{args.controller}".')

    spi_flash = None
    if args.spi_flash:
        with open(args.spi_flash, 'rb') as spi_flash_file:
            spi_flash = FlashMemory(spi_flash_file.read())

    # creates file if arg is given
    @contextmanager
    def get_output(path=None):
        """
        Opens file if path is given
        """
        if path is not None:
            file = open(path, 'wb')
            yield file
            file.close()
        else:
            yield None

    with get_output(args.log) as capture_file:
        loop = asyncio.get_event_loop()
        loop.run_until_complete(
            _main(controller, 
                console_bt_addr=args.console_bt_addr, 
                capture_file=capture_file, 
                spi_flash=spi_flash, 
                device_id=args.device_id
            )
        )
