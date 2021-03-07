import asyncio
import logging

import numpy as np

from joycontrol import logging_default as log
from joycontrol.hid import get_blt_hid_device, AsyncHID
from joycontrol.report import OutputReport, OutputReportID, SubCommand, InputReport

logger = logging.getLogger(__name__)


async def _main():
    logger.info('Waiting for HID devices... Please connect one JoyCon (left OR right), '
                'or a Pro Controller over Bluetooth. '
                'Note: The bluez "input" plugin needs to be enabled (default)')

    controller = await get_blt_hid_device()
    logger.info(f'Found controller "{controller}".')

    timer = 0

    with AsyncHID(path=controller['path'], loop=loop) as hid_controller:
        # enable imu
        output_report = OutputReport()
        output_report.set_output_report_id(OutputReportID.SUB_COMMAND)
        output_report.set_sub_command(SubCommand.ENABLE_6AXIS_SENSOR)
        output_report.set_sub_command_data([0x01])
        output_report.set_timer(timer)
        timer += 1

        await hid_controller.write(bytes(output_report)[1:])

        # wait for ack
        while True:
            data = await hid_controller.read(50)
            report = InputReport([0xA1] + list(data))
            if report.get_input_report_id() == 0x21 and report.get_ack() == 0x80:
                logger.info(f'Ack received {report.get_reply_to_subcommand_id()}')
                break

        # switch to 0x30 input report mode
        output_report = OutputReport()
        output_report.set_output_report_id(OutputReportID.SUB_COMMAND)
        output_report.set_sub_command(SubCommand.SET_INPUT_REPORT_MODE)
        output_report.set_sub_command_data([0x30])
        output_report.set_timer(timer)
        timer += 1

        await hid_controller.write(bytes(output_report)[1:])

        # wait for ack
        while True:
            data = await hid_controller.read(50)
            report = InputReport([0xA1] + list(data))
            if report.get_input_report_id() == 0x21 and report.get_ack() == 0x80:
                logger.info(f'Ack received {report.get_reply_to_subcommand_id()}')
                break

        try:
            while True:
                data = await hid_controller.read(50)
                report = InputReport([0xA1] + list(data))
                acc, gyro = report.get_imu_data()
                print(np.array(acc))
                # print(report.data)

        except KeyboardInterrupt:
            pass

if __name__ == '__main__':
    # setup logging
    log.configure()

    loop = asyncio.get_event_loop()
    loop.run_until_complete(
        _main()
    )
