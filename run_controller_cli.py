import argparse
import asyncio
import logging
import os
from contextlib import contextmanager

from joycontrol import logging_default as log
from joycontrol.command_line_interface import ControllerCLI
from joycontrol.controller import Controller
from joycontrol.memory import FlashMemory
from joycontrol.protocol import controller_protocol_factory
from joycontrol.server import create_hid_server
from joycontrol.sharing import start_share_controller_server


logger = logging.getLogger(__name__)

transport, protocol = None, None
async def _main(controller, capture_file=None, spi_flash=None, device_id=None, share_controller_address=None):
    factory = controller_protocol_factory(controller, spi_flash=spi_flash)
    global transport, protocol
    transport, protocol = await create_hid_server(factory, 17, 19, capture_file=capture_file, device_id=device_id)

    controller_state = protocol.get_controller_state()

    if share_controller_address is not None:
        asyncio.ensure_future(start_share_controller_server(protocol, share_controller_address))

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
    log.configure(console_level=logging.DEBUG)

    parser = argparse.ArgumentParser()
    parser.add_argument('controller', help='JOYCON_R, JOYCON_L or PRO_CONTROLLER')
    parser.add_argument('-l', '--log')
    parser.add_argument('-d', '--device_id')
    parser.add_argument('--spi_flash')
    parser.add_argument('-s', '--share-controller', action="store_true",
        help="Optional. Set to true to share this controller")
    parser.add_argument('--share-controller-address', default=None, type=str,
        help='A Unix socket address (i.e. path) to share the controller to other process; '
             'defaults to /tmp/controller-<device_id>.sock')
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

    if args.share_controller:
        if args.share_controller_address is None:
            args.share_controller_address = "/tmp/controller-{}.sock".format(args.device_id)
    else:
        args.share_controller_address = None

    with get_output(args.log) as capture_file:
        loop = asyncio.get_event_loop()
        loop.run_until_complete(
            _main(
                controller, 
                capture_file=capture_file, 
                spi_flash=spi_flash, 
                device_id=args.device_id, 
                share_controller_address=args.share_controller_address
            )
        )
