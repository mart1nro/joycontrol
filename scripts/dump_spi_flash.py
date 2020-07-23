import argparse
import asyncio
import logging
import os
from contextlib import suppress

import hid

from joycontrol import logging_default as log, utils
from joycontrol.report import OutputReport, InputReport, SubCommand
from joycontrol.utils import AsyncHID

logger = logging.getLogger(__name__)

VENDOR_ID = 1406
PRODUCT_ID_JL = 8198
PRODUCT_ID_JR = 8199
PRODUCT_ID_PC = 8201


class DataReader:
    def __init__(self):
        self.pending_request = None
        self.timer = 0
        self._stop_reading = False

    def close(self):
        self._stop_reading = True

    async def send_spi_read_request(self, hid_device, offset, size):
        report = OutputReport()
        report.sub_0x10_spi_flash_read(offset, size)

        # event shall be set if data received
        reply_event = asyncio.Event()
        self.pending_request = (offset, size, reply_event)

        # send spi flash read request
        while True:
            report.set_timer(self.timer)
            self.timer += 1

            # remove 0xA2 output report padding byte since it's not needed for communication over hid library
            data = report.data[1:]
            await hid_device.write(bytes(data))

            # wait for data received, send again if time out occurs (1 sec)
            try:
                await asyncio.wait_for(reply_event.wait(), 1)
                self.pending_request = None
                break
            except asyncio.TimeoutError:
                continue

    async def receive_data(self, hid_device, output_file=None):
        while True:
            data = await hid_device.read(size=255, timeout=3)
            if self._stop_reading:
                break
            elif not data:
                continue

            # add byte for input report
            data = b'\xa1' + data

            input_report = InputReport(list(data))

            # check if input report is spi flash read reply
            if input_report.get_input_report_id() != 0x21:
                continue
            try:
                sub_command_id = input_report.get_reply_to_subcommand_id()
                if sub_command_id != SubCommand.SPI_FLASH_READ:
                    continue
            except NotImplementedError:
                continue

            assert input_report.get_ack() == 0x90

            reply = input_report.get_sub_command_reply_data()

            # parse offset
            offset = 0
            digit = 1
            for i in range(4):
                offset += reply[i] * digit
                digit *= 0x100

            size = reply[4]

            # parse spi flash data
            assert len(reply) >= 5+size
            spi_data = reply[5:5+size]

            # check if received data is currently requested
            if self.pending_request is None or self.pending_request[0] != offset or self.pending_request[1] != size:
                continue

            # notify spi request sender that the data is received
            self.pending_request[2].set()

            logger.info(f'received offset {offset}, size {size} - {spi_data}')

            # write data to file
            if output_file is not None:
                output_file.write(bytes(spi_data))


async def dump_spi_flash(hid_device, output_file=None):
    SPI_FLASH_SIZE = 0x80000

    spi_flash_reader = DataReader()
    reader = asyncio.ensure_future(spi_flash_reader.receive_data(hid_device, output_file=output_file))

    try:
        # read data in 0x1D chunks
        for i in range(SPI_FLASH_SIZE // 0x1D):
            await spi_flash_reader.send_spi_read_request(hid_device, i * 0x1D, 0x1D)

        remainder = SPI_FLASH_SIZE % 0x1D
        if remainder:
            await spi_flash_reader.send_spi_read_request(hid_device, SPI_FLASH_SIZE - 1 - remainder, remainder)
    except asyncio.CancelledError:
        pass
    finally:
        spi_flash_reader.close()
        # wait for reader to close
        await reader


async def _main(args, loop):
    logger.info('Waiting for HID devices... Please connect one JoyCon (left OR right), or a Pro Controller over Bluetooth. '
                'Note: The bluez "input" plugin needs to be enabled (default)')

    controller = None
    while controller is None:
        for device in hid.enumerate(0, 0):
            # looking for devices matching Nintendo's vendor id and JoyCon product id
            if device['vendor_id'] == VENDOR_ID and device['product_id'] in (PRODUCT_ID_JL, PRODUCT_ID_JR, PRODUCT_ID_PC):
                controller = device
                break
        else:
            await asyncio.sleep(2)

    logger.info(f'Found controller "{controller}".')

    with utils.get_output(path=args.output, open_flags='wb', default=None) as output:
        with AsyncHID(path=controller['path'], loop=loop) as hid_controller:
            await dump_spi_flash(hid_controller, output_file=output)


if __name__ == '__main__':
    # check if root
    if not os.geteuid() == 0:
        raise PermissionError('Script must be run as root!')

    parser = argparse.ArgumentParser()
    parser.add_argument('output')
    args = parser.parse_args()

    # setup logging
    log.configure()

    loop = asyncio.get_event_loop()
    task = asyncio.ensure_future(_main(args, loop))

    try:
        loop.run_until_complete(task)
    except KeyboardInterrupt:
        task.cancel()
        with suppress(asyncio.CancelledError):
            loop.run_until_complete(task)
    finally:
        loop.stop()
        loop.close()
