import asyncio
import logging
import os

from joycontrol import logging_default as log
from joycontrol.controller_state import ControllerState, button_push
from joycontrol.protocol import controller_protocol_factory, Controller
from joycontrol.server import create_hid_server

logger = logging.getLogger(__name__)


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
