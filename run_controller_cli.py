#!/usr/bin/env python3

import argparse
import asyncio
import logging
import os

from aioconsole import ainput

from joycontrol import logging_default as log, utils
from joycontrol.command_line_interface import ControllerCLI
from joycontrol.controller import Controller
from joycontrol.controller_state import ControllerState, button_push, button_press, button_release
from joycontrol.memory import FlashMemory
from joycontrol.protocol import controller_protocol_factory
from joycontrol.server import create_hid_server

logger = logging.getLogger(__name__)

"""Emulates Switch controller. Opens joycontrol.command_line_interface to send button commands and more.

While running the cli, call "help" for an explanation of available commands.

Usage:
    run_controller_cli.py <controller> [--device_id | -d  <bluetooth_adapter_id>]
                                       [--spi_flash <spi_flash_memory_file>]
                                       [--reconnect_bt_addr | -r <console_bluetooth_address>]
                                       [--log | -l <communication_log_file>]
                                       [--nfc <nfc_data_file>]
    run_controller_cli.py -h | --help

Arguments:
    controller      Choose which controller to emulate. Either "JOYCON_R", "JOYCON_L" or "PRO_CONTROLLER"

Options:
    -d --device_id <bluetooth_adapter_id>   ID of the bluetooth adapter. Integer matching the digit in the hci* notation
                                            (e.g. hci0, hci1, ...) or Bluetooth mac address of the adapter in string
                                            notation (e.g. "FF:FF:FF:FF:FF:FF").
                                            Note: Selection of adapters may not work if the bluez "input" plugin is
                                            enabled.

    --spi_flash <spi_flash_memory_file>     Memory dump of a real Switch controller. Required for joystick emulation.
                                            Allows displaying of JoyCon colors.
                                            Memory dumps can be created using the dump_spi_flash.py script.

    -r --reconnect_bt_addr <console_bluetooth_address>  Previously connected Switch console Bluetooth address in string
                                                        notation (e.g. "FF:FF:FF:FF:FF:FF") for reconnection.
                                                        Does not require the "Change Grip/Order" menu to be opened,

    -l --log <communication_log_file>       Write hid communication (input reports and output reports) to a file.

    --nfc <nfc_data_file>                   Sets the nfc data of the controller to a given nfc dump upon initial
                                            connection.
"""


async def test_controller_buttons(controller_state: ControllerState):
    """
    Example controller script.
    Navigates to the "Test Controller Buttons" menu and presses all buttons.
    """
    if controller_state.get_controller() != Controller.PRO_CONTROLLER:
        raise ValueError('This script only works with the Pro Controller!')

    # waits until controller is fully connected
    await controller_state.connect()

    await ainput(prompt='Make sure the Switch is in the Home menu and press <enter> to continue.')

    """
    # We assume we are in the "Change Grip/Order" menu of the switch
    await button_push(controller_state, 'home')

    # wait for the animation
    await asyncio.sleep(1)
    """

    # Goto settings
    await button_push(controller_state, 'down', sec=1)
    await button_push(controller_state, 'right', sec=2)
    await asyncio.sleep(0.3)
    await button_push(controller_state, 'left')
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

    user_input = asyncio.ensure_future(
        ainput(prompt='Pressing all buttons... Press <enter> to stop.')
    )

    # push all buttons consecutively until user input
    while not user_input.done():
        for button in button_list:
            await button_push(controller_state, button)
            await asyncio.sleep(0.1)

            if user_input.done():
                break

    # await future to trigger exceptions in case something went wrong
    await user_input

    # go back to home
    await button_push(controller_state, 'home')


def ensure_valid_button(controller_state, *buttons):
    """
    Raise ValueError if any of the given buttons os not part of the controller state.
    :param controller_state:
    :param buttons: Any number of buttons to check (see ButtonState.get_available_buttons)
    """
    for button in buttons:
        if button not in controller_state.button_state.get_available_buttons():
            raise ValueError(f'Button {button} does not exist on {controller_state.get_controller()}')


async def mash_button(controller_state, button, interval):
    # wait until controller is fully connected
    await controller_state.connect()
    ensure_valid_button(controller_state, button)

    user_input = asyncio.ensure_future(
        ainput(prompt=f'Pressing the {button} button every {interval} seconds... Press <enter> to stop.')
    )
    # push a button repeatedly until user input
    while not user_input.done():
        await button_push(controller_state, button)
        await asyncio.sleep(float(interval))

    # await future to trigger exceptions in case something went wrong
    await user_input


def _register_commands_with_controller_state(controller_state, cli):
    """
    Commands registered here can use the given controller state.
    The doc string of commands will be printed by the CLI when calling "help"
    :param cli:
    :param controller_state:
    """
    async def test_buttons():
        """
        test_buttons - Navigates to the "Test Controller Buttons" menu and presses all buttons.
        """
        await test_controller_buttons(controller_state)

    cli.add_command(test_buttons.__name__, test_buttons)

    # Mash a button command
    async def mash(*args):
        """
        mash - Mash a specified button at a set interval

        Usage:
            mash <button> <interval>
        """
        if not len(args) == 2:
            raise ValueError('"mash_button" command requires a button and interval as arguments!')

        button, interval = args
        await mash_button(controller_state, button, interval)

    cli.add_command(mash.__name__, mash)

    # Hold a button command
    async def hold(*args):
        """
        hold - Press and hold specified buttons

        Usage:
            hold <button>

        Example:
            hold a b
        """
        if not args:
            raise ValueError('"hold" command requires a button!')

        ensure_valid_button(controller_state, *args)

        # wait until controller is fully connected
        await controller_state.connect()
        await button_press(controller_state, *args)

    cli.add_command(hold.__name__, hold)

    # Release a button command
    async def release(*args):
        """
        release - Release specified buttons

        Usage:
            release <button>

        Example:
            release a b
        """
        if not args:
            raise ValueError('"release" command requires a button!')

        ensure_valid_button(controller_state, *args)

        # wait until controller is fully connected
        await controller_state.connect()
        await button_release(controller_state, *args)

    cli.add_command(release.__name__, release)

    # Create nfc command
    async def nfc(*args):
        """
        nfc - Sets nfc content

        Usage:
            nfc <file_name>          Set controller state NFC content to file
            nfc remove               Remove NFC content from controller state
        """
        logger.error('NFC Support was removed from joycontrol - see https://github.com/mart1nro/joycontrol/issues/80')
        if controller_state.get_controller() == Controller.JOYCON_L:
            raise ValueError('NFC content cannot be set for JOYCON_L')
        elif not args:
            raise ValueError('"nfc" command requires file path to an nfc dump as argument!')
        elif args[0] == 'remove':
            controller_state.set_nfc(None)
            print('Removed nfc content.')
        else:
            _loop = asyncio.get_event_loop()
            with open(args[0], 'rb') as nfc_file:
                content = await _loop.run_in_executor(None, nfc_file.read)
                controller_state.set_nfc(content)

    cli.add_command(nfc.__name__, nfc)


async def _main(args):
    # parse the spi flash
    if args.spi_flash:
        with open(args.spi_flash, 'rb') as spi_flash_file:
            spi_flash = FlashMemory(spi_flash_file.read())
    else:
        # Create memory containing default controller stick calibration
        spi_flash = FlashMemory()

    # Get controller name to emulate from arguments
    controller = Controller.from_arg(args.controller)

    with utils.get_output(path=args.log, default=None) as capture_file:
        # prepare the the emulated controller
        factory = controller_protocol_factory(controller, spi_flash=spi_flash)
        ctl_psm, itr_psm = 17, 19
        transport, protocol = await create_hid_server(factory, reconnect_bt_addr=args.reconnect_bt_addr,
                                                      ctl_psm=ctl_psm,
                                                      itr_psm=itr_psm, capture_file=capture_file,
                                                      device_id=args.device_id)

        controller_state = protocol.get_controller_state()

        # Create command line interface and add some extra commands
        cli = ControllerCLI(controller_state)
        _register_commands_with_controller_state(controller_state, cli)
        cli.add_command('amiibo', ControllerCLI.deprecated('Command was removed - use "nfc" instead!'))

        # set default nfc content supplied by argument
        if args.nfc is not None:
            await cli.commands['nfc'](args.nfc)

        # run the cli
        try:
            await cli.run()
        finally:
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
    parser.add_argument('-r', '--reconnect_bt_addr', type=str, default=None,
                        help='The Switch console Bluetooth address, for reconnecting as an already paired controller')
    parser.add_argument('--nfc', type=str, default=None)
    args = parser.parse_args()

    loop = asyncio.get_event_loop()
    loop.run_until_complete(
        _main(args)
    )
