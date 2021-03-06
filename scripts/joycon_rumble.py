import asyncio
import logging
import os

from joycontrol import logging_default as log
from joycontrol.hid import get_blt_hid_device, AsyncHID
from joycontrol.report import InputReport, OutputReport, OutputReportID, SubCommand

logger = logging.getLogger(__name__)

"""
Sends some vibration reports to a joycon. Only works with the right joycon atm. 
"""


async def print_outputs(hid_device):
    while True:
        data = await hid_device.read(255)
        # add byte for input report
        data = b'\xa1' + data

        input_report = InputReport(list(data))
        vibrator_input = input_report.data[13]
        # print(hex(vibrator_input))


async def send_vibration_report(hid_device):
    reader = asyncio.ensure_future(print_outputs(hid_device))

    CHANGE_INPUT_REPORT_MODE = [1, 8, 0, 0, 0, 0, 0, 1, 64, 64, 3, 48, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
                                0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
    data = CHANGE_INPUT_REPORT_MODE
    print('writing', data)
    await hid_device.write(bytes(data))
    await asyncio.sleep(0.1)

    report = OutputReport()
    report.set_timer(1)
    report.set_output_report_id(OutputReportID.SUB_COMMAND)
    report.set_sub_command(SubCommand.ENABLE_VIBRATION)
    report.set_sub_command_data([0x01])
    data = bytes(report)[1:]

    print('writing', data)
    await hid_device.write(bytes(data))
    await asyncio.sleep(0.1)

    scale = [261.63, 293.66, 329.63, 349.23, 392.00, 440.00, 493.88, 523.25]
    scale = [int(round(n)) for n in scale]

    amp = 1
    time = 2
    while True:
        rumble_report = OutputReport()
        report.set_timer(time)
        time += 1
        rumble_report.set_output_report_id(OutputReportID.RUMBLE_ONLY)
        # increase frequency
        rumble_report.set_right_rumble_data(scale[time % len(scale)], amp)
        data = bytes(rumble_report)[1:]
        print('writing', data)
        await hid_device.write(bytes(data))

        await asyncio.sleep(.2)

    try:
        await reader
    except KeyboardInterrupt:
        pass


async def _main(loop):
    logger.info('Waiting for HID devices... Please connect one JoyCon (left OR right), '
                'or a Pro Controller over Bluetooth. '
                'Note: The bluez "input" plugin needs to be enabled (default)')

    controller = await get_blt_hid_device()
    logger.info(f'Found controller "{controller}".')

    with AsyncHID(path=controller['path'], loop=loop) as hid_controller:
        await send_vibration_report(hid_controller)


if __name__ == '__main__':
    # check if root
    if os.geteuid() != 0:
        raise PermissionError('Script must be run as root!')

    # h = lambda bla: list(map(hex, bla))
    # report = OutputReport()
    # report.set_left_rumble_data(1253, 0.012)
    # exit()

    # setup logging
    log.configure()

    loop = asyncio.get_event_loop()
    task = asyncio.ensure_future(_main(loop))

    try:
        loop.run_until_complete(task)
    except KeyboardInterrupt:
        task.cancel()
        try:
            loop.run_until_complete(task)
        except asyncio.CancelledError:
            pass
    finally:
        loop.stop()
        loop.close()
