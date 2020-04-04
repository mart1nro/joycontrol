import argparse
import asyncio
import logging
import os
from contextlib import contextmanager, suppress

from joycontrol import logging_default as log
from joycontrol.controller_state import ControllerState, button_push
from joycontrol.protocol import controller_protocol_factory, Controller
from joycontrol.server import create_hid_server
from joycontrol.transport import NotConnectedError

logger = logging.getLogger(__name__)


async def test_controller_buttons(controller_state: ControllerState):
    """
    Navigates to the "Test Controller Buttons" menu and presses all buttons.
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
    await button_push(controller_state, 'down', sec=4)
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

    # push all buttons except home and capture
    button_list = controller_state.button_state.get_available_buttons()
    if 'capture' in button_list:
        button_list.remove('capture')
    if 'home' in button_list:
        button_list.remove('home')

    # push all buttons consecutively
    while True:
        for button in button_list:
            await button_push(controller_state, button)
            await asyncio.sleep(0.1)


async def _main(controller, capture_file=None, spi_flash=None, device_id=None):
    factory = controller_protocol_factory(controller, spi_flash=spi_flash)
    transport, protocol = await create_hid_server(factory, 17, 19, capture_file=capture_file, device_id=device_id)

    try:
        await test_controller_buttons(protocol.get_controller_state())
    except KeyboardInterrupt:
        pass
    except NotConnectedError:
        logger.error('Connection was lost.')
    finally:
        logger.info('Stopping communication...')
        await transport.close()


if __name__ == '__main__':
    # check if root
    if not os.geteuid() == 0:
        raise PermissionError('Script must be run as root!')

    # setup logging
    log.configure()

    parser = argparse.ArgumentParser()
    #parser.add_argument('controller', help='JOYCON_R, JOYCON_L or PRO_CONTROLLER')
    parser.add_argument('-d', '--device_id')
    parser.add_argument('-l', '--log')
    parser.add_argument('--spi_flash')
    args = parser.parse_args()

    """
    if args.controller == 'JOYCON_R':
        controller = Controller.JOYCON_R
    elif args.controller == 'JOYCON_L':
        controller = Controller.JOYCON_L
    elif args.controller == 'PRO_CONTROLLER':
        controller = Controller.PRO_CONTROLLER
    else:
        raise ValueError(f'Unknown controller "{args.controller}".')
    """
    controller = Controller.PRO_CONTROLLER

    spi_flash = None
    if args.spi_flash:
        with open(args.spi_flash, 'rb') as spi_flash_file:
            spi_flash = spi_flash_file.read()

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

        main_function = asyncio.ensure_future(
            _main(controller, capture_file=capture_file, spi_flash=spi_flash, device_id=args.device_id)
        )

        # run main function until keyboard interrupt
        try:
            loop.run_until_complete(main_function)
        except KeyboardInterrupt:
            pass
        finally:
            # make sure main function has a chance to clean up
            with suppress(asyncio.CancelledError):
                main_function.cancel()
                loop.run_until_complete(
                    main_function
                )
