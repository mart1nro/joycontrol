import asyncio
import logging
import time
from asyncio import BaseTransport, BaseProtocol
from typing import Optional, Union, Tuple, Text
import math

import enum
import joycontrol.debug as debug
import socket
import joycontrol.utils as utils
import struct
from joycontrol.controller import Controller
from joycontrol.controller_state import ControllerState
from joycontrol.memory import FlashMemory
from joycontrol.report import OutputReport, SubCommand, InputReport, OutputReportID
from joycontrol.transport import NotConnectedError
from joycontrol.mcu import MicroControllerUnit

logger = logging.getLogger(__name__)


def controller_protocol_factory(controller: Controller, spi_flash=None, reconnect = False):
    if isinstance(spi_flash, bytes):
        spi_flash = FlashMemory(spi_flash_memory_data=spi_flash)

    def create_controller_protocol():
        return ControllerProtocol(controller, spi_flash=spi_flash, reconnect = reconnect)

    return create_controller_protocol

class SwitchState(enum.Enum):
    STANDARD = enum.auto,
    GRIP_MENU = enum.auto,
    AWAITING_MAX_SLOTS = enum.auto

close_pairing_menu_map = {
    Controller.JOYCON_R: ['x', 'a', 'home'],
    Controller.JOYCON_L: ['down', 'left'],
    Controller.PRO_CONTROLLER: ['a', 'b', 'home']
}

close_pairing_masks = {
    Controller.JOYCON_R: int.from_bytes(bytes([0x2 | 0x8, 0x10, 0]), "big"),
    Controller.JOYCON_L: int.from_bytes(bytes([0, 0, 0x1 | 0x8]), "big"),
    Controller.PRO_CONTROLLER: int.from_bytes(bytes([0x4 | 0x8, 0x10, 0]), "big")
}

class ControllerProtocol(BaseProtocol):
    def __init__(self, controller: Controller, spi_flash: FlashMemory = None, reconnect = False):
        self.controller = controller
        self.spi_flash = spi_flash
        self.transport = None

        # time when the timer started.
        self._input_report_timer_start = None

        self._controller_state = ControllerState(self, controller, spi_flash=spi_flash)
        self._controller_state_sender = None
        self._writer_thread = None

        self._mcu = MicroControllerUnit(self._controller_state)

        self._is_pairing = not reconnect

        # input mode
        self.delay_map = {
            None: math.inf, # subcommands only
            0x3F: 1.0,
            0x21: math.inf, # shouldn't happen
            0x30: 1/60, # this needs revising, but 120 seems too fast
        #    0x30: 1/120 if self.controller == Controller.PRO_CONTROLLER else 1/60,
            0x31: 1/60
        }
        self._input_report_wakeup = asyncio.Event()
        self._set_mode(None)

        # "Pausing"-mechanism.
        self._not_paused = asyncio.Event()
        self._not_paused.set()

        self.sig_input_ready = asyncio.Event()
        self.sig_data_received = asyncio.Event()

# INTERNAL

    def _set_mode(self, mode, delay=None):

        if mode == 0x21:
            logger.error("Shouldn't go into subcommand mode")

        self._input_report_mode = mode
        if delay:
            self.send_delay = self.delay_map[mode]
        elif self._is_pairing:
            self.send_delay = 1/15
        elif mode in self.delay_map:
            self.send_delay = self.delay_map[mode]
        else:
            logger.warning(f"Unknown delay for mode {mode}, assuming 1/15")
            self.send_delay = 1/15

        if mode in [0x30, 0x31, 0x32, 0x33]:
            # sig input ready, writer
            pass

        self._input_report_wakeup.set()

    async def _write(self, input_report):
        """
        Fires sig_is_send event in the controller state afterwards.

        Raises NotConnected exception if the transport is not connected or the connection was lost.
        """
        if self.transport is None:
            raise NotConnectedError('Transport not registered.')

        if self._is_pairing and (int.from_bytes(input_report.data[4:7], "big") & close_pairing_masks[self.controller]):
            # this is a bit too early, but so far no
            logger.info('left change Grip/Order menu')
            self._is_pairing = False
            self._set_mode(self._input_report_mode)

        if not self._not_paused.is_set():
            logger.warning("Write while paused")

        await self.transport.write(input_report)

        self._controller_state.sig_is_send.set()

    def _generate_input_report(self, mode=None):
        input_report = InputReport()
        if not mode:
            mode = self._input_report_mode

        if not mode:
            raise ValueError("cannot generate Report without Mode")

        input_report.set_input_report_id(mode)
        if mode == 0x3F:
            input_report.data[1:3] = [0x28, 0xca, 0x08]
            input_report.data[4:11] = [0x40,0x8A, 0x4F, 0x8A, 0xD0, 0x7E, 0xDF, 0x7F]
        else:
            if self._input_report_timer_start:
                input_report.set_timer(round((time.time() - self._input_report_timer_start) / 0.005) % 0x100)
            else:
                input_report.set_timer(0)
            input_report.set_misc()
            input_report.set_button_status(self._controller_state.button_state)
            input_report.set_stick_status(self._controller_state.l_stick_state, self._controller_state.r_stick_state)
            input_report.set_vibrator_input()
            if mode == 0x21:
                pass # subcommand is set outside
            elif mode in [0x30, 0x31, 0x32, 0x33]:
                input_report.set_6axis_data()

            if mode == 0x31:
                input_report.set_ir_nfc_data(self._mcu.get_data())
        return input_report

    async def _writer(self):
        """
        This continuously sends input reports to the switch.
        This relies on the asyncio scheduler to sneak the additional
        subcommand-replies in
        """
        logger.info("writer started")
        while self.transport:
            await self._not_paused.wait()
            last_send_time = time.time()
            input_report = self._generate_input_report()
            try:
                await self._write(input_report)
            except:
                break
            # calculate delay
            self.send_delay = debug.get_delay(self.send_delay) #debug hook
            active_time = time.time() - last_send_time
            sleep_time = self.send_delay - active_time
            if sleep_time < 0:
                logger.warning(f'Code is running {abs(sleep_time)} s too slow!')
                sleep_time = 0

            try:
                await asyncio.wait_for(self._input_report_wakeup.wait(), timeout=sleep_time)
                self._input_report_wakeup.clear()
            except asyncio.TimeoutError as err:
                pass

        logger.warning("Writer exited...")
        return None

    async def _reply_to_sub_command(self, report):
        # classify sub command
        try:
            sub_command = report.get_sub_command()
        except NotImplementedError as err:
            logger.warning(err)
            return False

        if sub_command is None:
            raise ValueError('Received output report does not contain a sub command')

        logging.info(f'received Sub command {sub_command}')

        sub_command_data = report.get_sub_command_data()
        assert sub_command_data is not None

        response_report = self._generate_input_report(mode=0x21)

        try:
            # answer to sub command
            if sub_command == SubCommand.REQUEST_DEVICE_INFO:
                await self._command_request_device_info(response_report, sub_command_data)

            elif sub_command == SubCommand.SET_SHIPMENT_STATE:
                await self._command_set_shipment_state(response_report, sub_command_data)

            elif sub_command == SubCommand.SPI_FLASH_READ:
                await self._command_spi_flash_read(response_report, sub_command_data)

            elif sub_command == SubCommand.SET_INPUT_REPORT_MODE:
                await self._command_set_input_report_mode(response_report, sub_command_data)

            elif sub_command == SubCommand.TRIGGER_BUTTONS_ELAPSED_TIME:
                await self._command_trigger_buttons_elapsed_time(response_report, sub_command_data)

            elif sub_command == SubCommand.ENABLE_6AXIS_SENSOR:
                await self._command_enable_6axis_sensor(response_report, sub_command_data)

            elif sub_command == SubCommand.ENABLE_VIBRATION:
                await self._command_enable_vibration(response_report, sub_command_data)

            elif sub_command == SubCommand.SET_NFC_IR_MCU_CONFIG:
                await self._command_set_nfc_ir_mcu_config(response_report, sub_command_data)

            elif sub_command == SubCommand.SET_NFC_IR_MCU_STATE:
                await self._command_set_nfc_ir_mcu_state(response_report, sub_command_data)

            elif sub_command == SubCommand.SET_PLAYER_LIGHTS:
                await self._command_set_player_lights(response_report, sub_command_data)
            else:
                logger.warning(f'Sub command 0x{sub_command.value:02x} not implemented - ignoring')
                return False

            await self._write(response_report)

        except NotImplementedError as err:
            logger.error(f'Failed to answer {sub_command} - {err}')
            return False
        return True

# transport hooks

    def connection_made(self, transport: BaseTransport) -> None:
        logger.debug('Connection established.')
        self.transport = transport
        self._input_report_timer_start = time.time()

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

    async def report_received(self, data: Union[bytes, Text], addr: Tuple[str, int]) -> None:
        self.sig_data_received.set()

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
        elif output_report_id == OutputReportID.RUMBLE_ONLY:
            # TODO Rumble
            pass
        elif output_report_id == OutputReportID.REQUEST_IR_NFC_MCU:
            self._mcu.received_11(report.data[11], report.get_sub_command_data())
            pass
        else:
            logger.warning(f'Output report {output_report_id} not implemented - ignoring')


# event lisnter hooks

    async def send_controller_state(self):
        """
        Waits for the controller state to be send.

        Raises NotConnected exception if the transport is not connected or the connection was lost.
        """
        # TODO: Call write directly if in continuously sending input report mode

        if self.transport is None:
            raise NotConnectedError('Transport not registered.')

        if not self._not_paused.is_set():
            await self._write(self._generate_input_report())
        else:
            self._controller_state.sig_is_send.clear()

            # wrap into a future to be able to set an exception in case of a disconnect
            self._controller_state_sender = asyncio.ensure_future(self._controller_state.sig_is_send.wait())
            await self._controller_state_sender
            self._controller_state_sender = None

    async def wait_for_output_report(self):
        """
        Waits until an output report from the Switch is received.
        """
        self.sig_data_received.clear()
        await self.sig_data_received.wait()

    def pause(self):
        logger.info("paused")
        self._not_paused.clear()

    def unpause(self):
        logger.info("unpaused")
        self._not_paused.set()

    def get_controller_state(self) -> ControllerState:
        return self._controller_state

# subcommands

    async def _command_request_device_info(self, input_report, sub_command_data):

        address = self.transport.get_extra_info('sockname')
        assert address is not None
        bd_address = list(map(lambda x: int(x, 16), address[0].split(':')))

        input_report.set_ack(0x82)
        input_report.sub_0x02_device_info(bd_address, controller=self.controller)

        return input_report

    async def _command_set_shipment_state(self, input_report, sub_command_data):
        input_report.set_ack(0x80)
        input_report.reply_to_subcommand_id(0x08)
        return input_report

    async def _command_spi_flash_read(self, input_report, sub_command_data):
        """
        Replies with 0x21 input report containing requested data from the flash memory.
        :param sub_command_data: input report sub command data bytes
        """
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

        return input_report

    async def _command_set_input_report_mode(self, input_report, sub_command_data):
        if self._input_report_mode == sub_command_data[0]:
            logger.warning(f'Already in input report mode {sub_command_data[0]} - ignoring request')

        self._set_mode(sub_command_data[0])

        # Send acknowledgement

        input_report.set_ack(0x80)
        input_report.reply_to_subcommand_id(0x03)

        return input_report

    async def _command_trigger_buttons_elapsed_time(self, input_report, sub_command_data):
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

        return input_report

    async def _command_enable_6axis_sensor(self, input_report, sub_command_data):
        input_report.set_ack(0x80)
        input_report.reply_to_subcommand_id(0x40)

        return input_report

    async def _command_enable_vibration(self, input_report, sub_command_data):
        input_report.set_ack(0x80)
        input_report.reply_to_subcommand_id(SubCommand.ENABLE_VIBRATION.value)

        return input_report

    async def _command_set_nfc_ir_mcu_config(self, input_report, sub_command_data):
        self._mcu.set_config_cmd(sub_command_data)

        input_report.set_ack(0xA0)
        input_report.reply_to_subcommand_id(SubCommand.SET_NFC_IR_MCU_CONFIG.value)

        data = [1, 0, 255, 0, 8, 0, 27, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 200]
        for i in range(len(data)):
            input_report.data[16 + i] = data[i]

        return input_report

    async def _command_set_nfc_ir_mcu_state(self, input_report, sub_command_data):
        self._mcu.set_power_state_cmd(sub_command_data[0])

        if sub_command_data[0] == 0x01:
            # 0x01 = Resume
            input_report.set_ack(0x80)
            input_report.reply_to_subcommand_id(SubCommand.SET_NFC_IR_MCU_STATE.value)
        elif sub_command_data[0] == 0x00:
            # 0x00 = Suspend
            input_report.set_ack(0x80)
            input_report.reply_to_subcommand_id(SubCommand.SET_NFC_IR_MCU_STATE.value)
        else:
            raise NotImplementedError(f'Argument {sub_command_data[0]} of {SubCommand.SET_NFC_IR_MCU_STATE} '
                                      f'not implemented.')
        return input_report

    async def _command_set_player_lights(self, input_report, sub_command_data):
        input_report.set_ack(0x80)
        input_report.reply_to_subcommand_id(SubCommand.SET_PLAYER_LIGHTS.value)

        self._writer_thread = utils.start_asyncio_thread(self._writer())
        self.sig_input_ready.set()
        return input_report
