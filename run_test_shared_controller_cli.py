import argparse
import asyncio
import logging
import os
from contextlib import contextmanager

from joycontrol import logging_default as log
from joycontrol.command_line_interface import ControllerCLI
from joycontrol.memory import FlashMemory
from joycontrol.sharing import get_shared_controller

async def _main(server_address, capture_file=None):
    # We don't need to catch anything here
    # just raise and exit the program if fails to connect
    protocol, server_conn = await get_shared_controller(server_address, capture_file=capture_file)

    print("You are using a shared controller. "
      "You may exit the program at any time to yield the controller back to the sharing server.")

    controller_state = protocol.get_controller_state()
    cli = ControllerCLI(controller_state)
    await cli.run()

    logger.info('Yielding controller back to the sharing server...')
    server_conn.close()

if __name__ == '__main__':
    # check if root
    if not os.geteuid() == 0:
        raise PermissionError('Script must be run as root!')

    # setup logging
    #log.configure(console_level=logging.ERROR)
    log.configure()

    parser = argparse.ArgumentParser()
    parser.add_argument('-l', '--log')
    parser.add_argument('--share-controller-address', default="/tmp/controller-None.sock", type=str,
        help='A Unix socket address (i.e. path) to share the controller to other process')
    args = parser.parse_args()

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
            _main(
                args.share_controller_address, 
                capture_file=capture_file, 
            )
        )
