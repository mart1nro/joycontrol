import asyncio
import logging
from asyncio import BaseTransport, BaseProtocol
from typing import Optional, Union, Tuple, Text

from joycontrol.controller import Controller
from joycontrol.controller_state import ControllerState
from joycontrol.report import OutputReport, SubCommand, InputReport, OutputReportID

logger = logging.getLogger(__name__)


def controller_protocol_factory(controller: Controller):
    def create_controller_protocol():
        return ControllerProtocol(controller)
    return create_controller_protocol


class ControllerProtocol(BaseProtocol):
    def __init__(self, controller: Controller):
        self.controller = controller

        self.transport = None

        self._data_received = asyncio.Event()

        self._controller_state = ControllerState(self)

        self._pending_write = None
        self._pending_input_report = None

        self._0x30_input_report_sender = None

        self.sig_wait_player_lights = asyncio.Event()

    async def write(self, input_report: InputReport):
        # set button and TODO: stick date
        if self._controller_state.button_state is not None:
            input_report.set_button_status(self._controller_state.button_state)
        self._controller_state.sig_is_send.set()

        await self.transport.write(input_report)

    def get_controller_state(self):
        return self._controller_state

    async def wait_for_output_report(self):
        self._data_received.clear()
        await self._data_received.wait()

    def connection_made(self, transport: BaseTransport) -> None:
        logger.debug('Connection established.')
        self.transport = transport

    def connection_lost(self, exc: Optional[Exception]) -> None:
        raise NotImplementedError()

    def error_received(self, exc: Exception) -> None:
        raise NotImplementedError()

    async def send_0x30_input_reports(self):
        input_report = InputReport()
        input_report.set_input_report_id(0x30)
        input_report.set_misc()

        while True:
            # TODO: set sensor data
            input_report.set_6axis_data()

            await self.write(input_report)

            """
            if self.controller == Controller.PRO_CONTROLLER:
                # send state at 120Hz if Pro Controller
                await asyncio.sleep(1 / 120)
            else:
                # send state at 60Hz
                await asyncio.sleep(1 / 60)
            """
            await asyncio.sleep(1 / 30)

    async def report_received(self, data: Union[bytes, Text], addr: Tuple[str, int]) -> None:
        self._data_received.set()

        try:
            report = OutputReport(list(data))
        except ValueError as v_err:
            logger.warning(f'Report parsing error "{v_err}" - IGNORE')
            return

        try:
            output_report_id = report.get_output_report_id()
        except NotImplementedError as err:
            logger.warning(err)
            return

        if output_report_id == OutputReportID.SUB_COMMAND:
            # classify sub command
            try:
                sub_command = report.get_sub_command()
            except NotImplementedError as err:
                logger.warning(err)
                return

            if sub_command is None:
                raise ValueError('Received output report does not contain a sub command')

            logging.info(f'received output report - Sub command {sub_command}')
            # answer to sub command
            if sub_command == SubCommand.REQUEST_DEVICE_INFO:
                await self._command_request_device_info(report)

            elif sub_command == SubCommand.SET_SHIPMENT_STATE:
                await self._command_set_shipment_state(report)

            elif sub_command == SubCommand.SPI_FLASH_READ:
                await self._command_spi_flash_read(report)

            elif sub_command == SubCommand.SET_INPUT_REPORT_MODE:
                await self._command_set_input_report_mode(report)

            elif sub_command == SubCommand.TRIGGER_BUTTONS_ELAPSED_TIME:
                await self._command_trigger_buttons_elapsed_time(report)

            elif sub_command == SubCommand.ENABLE_6AXIS_SENSOR:
                await self._command_enable_6axis_sensor(report)

            elif sub_command == SubCommand.ENABLE_VIBRATION:
                await self._command_enable_vibration(report)

            elif sub_command == SubCommand.SET_NFC_IR_MCU_CONFIG:
                await self._command_set_nfc_ir_mcu_config(report)

            elif sub_command == SubCommand.SET_PLAYER_LIGHTS:
                await self._command_set_player_lights(report)

            else:
                logger.warning(f'Sub command 0x{sub_command.value:02x} not implemented - ignoring')
        #elif output_report_id == OutputReportID.RUMBLE_ONLY:
        #    pass
        else:
            logger.warning(f'Output report {output_report_id} not implemented - ignoring')

    async def _command_request_device_info(self, output_report):
        input_report = InputReport()
        input_report.set_input_report_id(0x21)
        input_report.set_misc()

        address = self.transport.get_extra_info('sockname')
        assert address is not None
        bd_address = list(map(lambda x: int(x, 16), address[0].split(':')))

        input_report.set_ack(0x82)
        input_report.sub_0x02_device_info(bd_address, controller=self.controller)

        await self.write(input_report)

    async def _command_set_shipment_state(self, output_report):
        input_report = InputReport()
        input_report.set_input_report_id(0x21)
        input_report.set_misc()

        input_report.set_ack(0x80)
        input_report.reply_to_subcommand_id(0x08)

        await self.write(input_report)

    async def _command_spi_flash_read(self, output_report):
        input_report = InputReport()
        input_report.set_input_report_id(0x21)
        input_report.set_misc()

        input_report.set_ack(0x90)
        input_report.sub_0x10_spi_flash_read(output_report)

        await self.write(input_report)

    async def _command_set_input_report_mode(self, output_report):
        if output_report.data[12] == 0x30:
            logger.info('Setting input report mode to 0x30...')
            # start sending 0x30 input reports
            assert self._0x30_input_report_sender is None
            self._0x30_input_report_sender = asyncio.ensure_future(self.send_0x30_input_reports())

            input_report = InputReport()
            input_report.set_input_report_id(0x21)
            input_report.set_misc()

            input_report.set_ack(0x80)
            input_report.reply_to_subcommand_id(0x03)

            await self.write(input_report)
        else:
            logger.error(f'input report mode {output_report.data[12]} not implemented - ignoring request')

    async def _command_trigger_buttons_elapsed_time(self, output_report):
        input_report = InputReport()
        input_report.set_input_report_id(0x21)
        input_report.set_misc()

        input_report.set_ack(0x83)
        input_report.sub_0x04_trigger_buttons_elapsed_time()

        await self.write(input_report)

    async def _command_enable_6axis_sensor(self, output_report):
        input_report = InputReport()
        input_report.set_input_report_id(0x21)
        input_report.set_misc()

        input_report.set_ack(0x80)
        input_report.reply_to_subcommand_id(0x40)

        await self.write(input_report)

    async def _command_enable_vibration(self, output_report):
        input_report = InputReport()
        input_report.set_input_report_id(0x21)
        input_report.set_misc()

        input_report.set_ack(0x80)
        input_report.reply_to_subcommand_id(SubCommand.ENABLE_VIBRATION.value)

        await self.write(input_report)

    async def _command_set_nfc_ir_mcu_config(self, output_report):
        input_report = InputReport()
        input_report.set_input_report_id(0x21)
        input_report.set_misc()

        input_report.set_ack(0xA0)
        input_report.reply_to_subcommand_id(SubCommand.SET_NFC_IR_MCU_CONFIG.value)

        for i in range(16, 51):
            input_report.data[i] = 0xFF

        await self.write(input_report)

    async def _command_set_player_lights(self, output_report):
        input_report = InputReport()
        input_report.set_input_report_id(0x21)
        input_report.set_misc()

        input_report.set_ack(0x80)
        input_report.reply_to_subcommand_id(SubCommand.SET_PLAYER_LIGHTS.value)

        await self.write(input_report)

        self.sig_wait_player_lights.set()
