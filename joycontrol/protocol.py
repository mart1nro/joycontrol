import asyncio
import logging
from asyncio import BaseTransport, BaseProtocol
from contextlib import suppress
from typing import Optional, Union, Tuple, Text

from joycontrol import utils
from joycontrol.controller import Controller
from joycontrol.controller_state import ControllerState
from joycontrol.memory import FlashMemory
from joycontrol.report import OutputReport, SubCommand, InputReport, OutputReportID
from joycontrol.transport import NotConnectedError
from joycontrol.mcu import Mcu, McuState, Action
from crc8 import crc8

logger = logging.getLogger(__name__)


def controller_protocol_factory(controller: Controller, spi_flash=None):
    if isinstance(spi_flash, bytes):
        spi_flash = FlashMemory(spi_flash_memory_data=spi_flash)

    def create_controller_protocol():
        return ControllerProtocol(controller, spi_flash=spi_flash)

    return create_controller_protocol


class ControllerProtocol(BaseProtocol):
    def __init__(self, controller: Controller, spi_flash: FlashMemory = None):
        self.controller = controller
        self.spi_flash = spi_flash

        self.transport = None

        # Increases for each input report send, should overflow at 0x100
        self._input_report_timer = 0x00

        self._data_received = asyncio.Event()

        self._controller_state = ControllerState(self, controller, spi_flash=spi_flash)
        self._controller_state_sender = None

        self._mcu = Mcu()

        # None = Just answer to sub commands
        self._input_report_mode = None

        # This event gets triggered once the Switch assigns a player number to the controller and accepts user inputs
        self.sig_set_player_lights = asyncio.Event()

    async def send_controller_state(self):
        """
        Waits for the controller state to be send.

        Raises NotConnected exception if the transport is not connected or the connection was lost.
        """
        # TODO: Call write directly if not in 0x30 input report mode

        if self.transport is None:
            raise NotConnectedError('Transport not registered.')

        self._controller_state.sig_is_send.clear()

        # wrap into a future to be able to set an exception in case of a disconnect
        self._controller_state_sender = asyncio.ensure_future(self._controller_state.sig_is_send.wait())
        await self._controller_state_sender
        self._controller_state_sender = None

    async def write(self, input_report: InputReport):
        """
        Sets timer byte and current button state in the input report and sends it.
        Fires sig_is_send event in the controller state afterwards.

        Raises NotConnected exception if the transport is not connected or the connection was lost.
        """
        if self.transport is None:
            raise NotConnectedError('Transport not registered.')

        # set button and stick data of input report
        input_report.set_button_status(self._controller_state.button_state)
        if self._controller_state.l_stick_state is None:
            l_stick = [0x00, 0x00, 0x00]
        else:
            l_stick = self._controller_state.l_stick_state
        if self._controller_state.r_stick_state is None:
            r_stick = [0x00, 0x00, 0x00]
        else:
            r_stick = self._controller_state.r_stick_state
        input_report.set_stick_status(l_stick, r_stick)

        # set timer byte of input report
        input_report.set_timer(self._input_report_timer)
        self._input_report_timer = (self._input_report_timer + 1) % 0x100

        if input_report.get_input_report_id() == 0x31:
            self._mcu.set_nfc(self._controller_state._nfc_content)
            self._mcu.update_nfc_report()
            input_report.set_mcu(self._mcu)

        await self.transport.write(input_report)

        self._controller_state.sig_is_send.set()

    def get_controller_state(self) -> ControllerState:
        return self._controller_state

    async def wait_for_output_report(self):
        """
        Waits until an output report from the Switch is received.
        """
        self._data_received.clear()
        await self._data_received.wait()

    def connection_made(self, transport: BaseTransport) -> None:
        logger.debug('Connection established.')
        self.transport = transport

    def connection_lost(self, exc: Optional[Exception] = None) -> None:
        if self.transport is not None:
            logger.error('Connection lost.')
            asyncio.ensure_future(self.transport.close())
            self.transport = None

            if self._controller_state_sender is not None:
                self._controller_state_sender.set_exception(NotConnectedError)

    def error_received(self, exc: Exception) -> None:
        # TODO?
        raise NotImplementedError()

    async def input_report_mode_full(self):
        """
        Continuously sends full input reports containing the controller state.
        """
        if self.transport.is_reading():
            raise ValueError('Transport must be paused in full input report mode')

        input_report = InputReport()
        input_report.set_vibrator_input()
        input_report.set_misc()

        reader = asyncio.ensure_future(self.transport.read())

        try:
            while True:
                input_report.set_input_report_id(self._input_report_mode)
                # TODO: improve timing
                if self.controller == Controller.PRO_CONTROLLER:
                    # send state at 120Hz
                    await asyncio.sleep(1 / 120)
                else:
                    # send state at 60Hz
                    await asyncio.sleep(1 / 60)

                reply_send = False
                if reader.done():
                    data = await reader

                    reader = asyncio.ensure_future(self.transport.read())

                    try:
                        report = OutputReport(list(data))
                        output_report_id = report.get_output_report_id()

                        if output_report_id == OutputReportID.RUMBLE_ONLY:
                            # TODO
                            pass
                        elif output_report_id == OutputReportID.SUB_COMMAND:
                            reply_send = await self._reply_to_sub_command(report)
                        elif output_report_id == OutputReportID.REQUEST_MCU:
                            reply_send = await self._reply_to_mcu(report)
                        else:
                            logger.warning(f'Report unknown output report "{output_report_id}" - IGNORE')
                    except ValueError as v_err:
                        logger.warning(f'Report parsing error "{v_err}" - IGNORE')
                    except NotImplementedError as err:
                        logger.warning(err)

                if reply_send:
                    # Hack: Adding a delay here to avoid flooding during pairing
                    await asyncio.sleep(0.3)
                else:
                    # write 0x30 input report.
                    # TODO: set some sensor data
                    input_report.set_6axis_data()

                    await self.write(input_report)

        except NotConnectedError as err:
            # Stop 0x30 input report mode if disconnected.
            logger.error(err)
        finally:
            # cleanup
            self._input_report_mode = None
            # cancel the reader
            with suppress(asyncio.CancelledError, NotConnectedError):
                if reader.cancel():
                    await reader

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
            await self._reply_to_sub_command(report)
        # elif output_report_id == OutputReportID.RUMBLE_ONLY:
        #    pass
        else:
            logger.warning(f'Output report {output_report_id} not implemented - ignoring')

    async def _reply_to_mcu(self, report):
        sub_command = report.data[11]
        sub_command_data = report.data[12:]

        # logging.info(f'received output report - Request MCU sub command {sub_command}')

        if self._mcu.get_action() == Action.READ_TAG or self._mcu.get_action() == Action.READ_TAG_2 or self._mcu.get_action() == Action.READ_FINISHED:
            return

        # Request mcu state
        if sub_command == 0x01:
            # input_report = InputReport()
            # input_report.set_input_report_id(0x21)
            # input_report.set_misc()

            # input_report.set_ack(0xA0)
            # input_report.reply_to_subcommand_id(0x21)

            self._mcu.set_action(Action.REQUEST_STATUS)
            # input_report.set_mcu(self._mcu)

            # await self.write(input_report)
        # Send Start tag discovery
        elif sub_command == 0x02:
            # 0: Cancel all, 4: StartWaitingReceive
            if sub_command_data[0] == 0x04:
                self._mcu.set_action(Action.START_TAG_DISCOVERY)
            # 1: Start polling
            elif sub_command_data[0] == 0x01:
                self._mcu.set_action(Action.START_TAG_POLLING)
            # 2: stop polling
            elif sub_command_data[0] == 0x02:
                self._mcu.set_action(Action.NON)
            elif sub_command_data[0] == 0x06:
                self._mcu.set_action(Action.READ_TAG)
            else:
                logging.info(f'Unknown sub_command_data arg {sub_command_data}')
        else:
            logging.info(f'Unknown MCU sub command {sub_command}')

    async def _reply_to_sub_command(self, report):
        # classify sub command
        try:
            sub_command = report.get_sub_command()
        except NotImplementedError as err:
            logger.warning(err)
            return False

        if sub_command is None:
            raise ValueError('Received output report does not contain a sub command')

        logging.info(f'received output report - Sub command {sub_command}')

        sub_command_data = report.get_sub_command_data()
        assert sub_command_data is not None

        try:
            # answer to sub command
            if sub_command == SubCommand.REQUEST_DEVICE_INFO:
                await self._command_request_device_info(sub_command_data)

            elif sub_command == SubCommand.SET_SHIPMENT_STATE:
                await self._command_set_shipment_state(sub_command_data)

            elif sub_command == SubCommand.SPI_FLASH_READ:
                await self._command_spi_flash_read(sub_command_data)

            elif sub_command == SubCommand.SET_INPUT_REPORT_MODE:
                await self._command_set_input_report_mode(sub_command_data)

            elif sub_command == SubCommand.TRIGGER_BUTTONS_ELAPSED_TIME:
                await self._command_trigger_buttons_elapsed_time(sub_command_data)

            elif sub_command == SubCommand.ENABLE_6AXIS_SENSOR:
                await self._command_enable_6axis_sensor(sub_command_data)

            elif sub_command == SubCommand.ENABLE_VIBRATION:
                await self._command_enable_vibration(sub_command_data)

            elif sub_command == SubCommand.SET_NFC_IR_MCU_CONFIG:
                await self._command_set_nfc_ir_mcu_config(sub_command_data)

            elif sub_command == SubCommand.SET_NFC_IR_MCU_STATE:
                await self._command_set_nfc_ir_mcu_state(sub_command_data)

            elif sub_command == SubCommand.SET_PLAYER_LIGHTS:
                await self._command_set_player_lights(sub_command_data)
            else:
                logger.warning(f'Sub command 0x{sub_command.value:02x} not implemented - ignoring')
                return False
        except NotImplementedError as err:
            logger.error(f'Failed to answer {sub_command} - {err}')
            return False
        return True

    async def _command_request_device_info(self, sub_command_data):
        input_report = InputReport()
        input_report.set_input_report_id(0x21)
        input_report.set_misc()

        address = self.transport.get_extra_info('sockname')
        assert address is not None
        bd_address = list(map(lambda x: int(x, 16), address[0].split(':')))

        input_report.set_ack(0x82)
        input_report.sub_0x02_device_info(bd_address, controller=self.controller)

        await self.write(input_report)

    async def _command_set_shipment_state(self, sub_command_data):
        input_report = InputReport()
        input_report.set_input_report_id(0x21)
        input_report.set_misc()

        input_report.set_ack(0x80)
        input_report.reply_to_subcommand_id(0x08)

        await self.write(input_report)

    async def _command_spi_flash_read(self, sub_command_data):
        """
        Replies with 0x21 input report containing requested data from the flash memory.
        :param sub_command_data: input report sub command data bytes
        """
        input_report = InputReport()
        input_report.set_input_report_id(0x21)
        input_report.set_misc()

        input_report.set_ack(0x90)

        # parse offset
        offset = 0
        digit = 1
        for i in range(4):
            offset += sub_command_data[i] * digit
            digit *= 0x100

        size = sub_command_data[4]

        if self.spi_flash is not None:
            spi_flash_data = self.spi_flash[offset: offset + size]
            input_report.sub_0x10_spi_flash_read(offset, size, spi_flash_data)
        else:
            spi_flash_data = size * [0x00]
            input_report.sub_0x10_spi_flash_read(offset, size, spi_flash_data)

        await self.write(input_report)

    async def _command_set_input_report_mode(self, sub_command_data):
        if sub_command_data[0] == 0x30:
            pass
        elif sub_command_data[0] == 0x31:
            pass
        else:
            logger.error(f'input report mode {sub_command_data[0]} not implemented - ignoring request')
            return

        logger.info(f'Setting input report mode to {hex(sub_command_data[0])}...')

        input_report = InputReport()
        input_report.set_input_report_id(0x21)
        input_report.set_misc()

        input_report.set_ack(0x80)
        input_report.reply_to_subcommand_id(0x03)

        await self.write(input_report)

        # start sending input reports
        if self._input_report_mode is None:

            self.transport.pause_reading()
            new_reader = asyncio.ensure_future(self.input_report_mode_full())

            # We need to swap the reader in the future because this function was probably called by it
            async def set_reader():
                await self.transport.set_reader(new_reader)
                self.transport.resume_reading()

            asyncio.ensure_future(set_reader()).add_done_callback(
                utils.create_error_check_callback()
            )

        self._input_report_mode = sub_command_data[0]

    async def _command_trigger_buttons_elapsed_time(self, sub_command_data):
        input_report = InputReport()
        input_report.set_input_report_id(0x21)
        input_report.set_misc()

        input_report.set_ack(0x83)
        input_report.reply_to_subcommand_id(SubCommand.TRIGGER_BUTTONS_ELAPSED_TIME)
        # Hack: We assume this command is only used during pairing - Set values so the Switch assigns a player number
        if self.controller == Controller.PRO_CONTROLLER:
            input_report.sub_0x04_trigger_buttons_elapsed_time(L_ms=3000, R_ms=3000)
        elif self.controller in (Controller.JOYCON_L, Controller.JOYCON_R):
            # TODO: What do we do if we want to pair a combined JoyCon?
            input_report.sub_0x04_trigger_buttons_elapsed_time(SL_ms=3000, SR_ms=3000)
        else:
            raise NotImplementedError(self.controller)

        await self.write(input_report)

    async def _command_enable_6axis_sensor(self, sub_command_data):
        input_report = InputReport()
        input_report.set_input_report_id(0x21)
        input_report.set_misc()

        input_report.set_ack(0x80)
        input_report.reply_to_subcommand_id(0x40)

        await self.write(input_report)

    async def _command_enable_vibration(self, sub_command_data):
        input_report = InputReport()
        input_report.set_input_report_id(0x21)
        input_report.set_misc()

        input_report.set_ack(0x80)
        input_report.reply_to_subcommand_id(SubCommand.ENABLE_VIBRATION.value)

        await self.write(input_report)

    async def _command_set_nfc_ir_mcu_config(self, sub_command_data):
        input_report = InputReport()
        input_report.set_input_report_id(0x21)
        input_report.set_misc()

        input_report.set_ack(0xA0)
        input_report.reply_to_subcommand_id(SubCommand.SET_NFC_IR_MCU_CONFIG.value)

        self._mcu.update_status()
        data = list(bytes(self._mcu)[0:34])
        crc = crc8()
        crc.update(bytes(data[:-1]))
        checksum = crc.digest()
        data[-1] = ord(checksum)
    
        for i in range(len(data)):
            input_report.data[16+i] = data[i]
        
        # Set MCU mode cmd
        if sub_command_data[1] == 0:
            if sub_command_data[2] == 0:
                self._mcu.set_state(McuState.STAND_BY)
            elif sub_command_data[2] == 4:
                self._mcu.set_state(McuState.NFC)
            else:
                logger.info(f"unknown mcu state {sub_command_data[2]}")
        else:
            logger.info(f"unknown mcu config command {sub_command_data}")

        await self.write(input_report)

    async def _command_set_nfc_ir_mcu_state(self, sub_command_data):
        input_report = InputReport()
        input_report.set_input_report_id(0x21)
        input_report.set_misc()

        if sub_command_data[0] == 0x01:
            # 0x01 = Resume
            input_report.set_ack(0x80)
            input_report.reply_to_subcommand_id(SubCommand.SET_NFC_IR_MCU_STATE.value)
            self._mcu.set_action(Action.NON)
            self._mcu.set_state(McuState.STAND_BY)
        elif sub_command_data[0] == 0x00:
            # 0x00 = Suspend
            input_report.set_ack(0x80)
            input_report.reply_to_subcommand_id(SubCommand.SET_NFC_IR_MCU_STATE.value)
            self._mcu.set_state(McuState.STAND_BY)
        else:
            raise NotImplementedError(f'Argument {sub_command_data[0]} of {SubCommand.SET_NFC_IR_MCU_STATE} '
                                      f'not implemented.')

        await self.write(input_report)

    async def _command_set_player_lights(self, sub_command_data):
        input_report = InputReport()
        input_report.set_input_report_id(0x21)
        input_report.set_misc()

        input_report.set_ack(0x80)
        input_report.reply_to_subcommand_id(SubCommand.SET_PLAYER_LIGHTS.value)

        await self.write(input_report)

        self.sig_set_player_lights.set()
