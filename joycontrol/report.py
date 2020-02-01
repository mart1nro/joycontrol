import asyncio
from enum import Enum

from joycontrol.button_state import ButtonState
from joycontrol.controller import Controller


class InputReport:
    """
    Class to create Input Reports. Reference:
    https://github.com/dekuNukem/Nintendo_Switch_Reverse_Engineering/blob/master/bluetooth_hid_notes.md
    """
    def __init__(self):
        self.data = [0x00] * 51
        # all input reports are prepended with 0xA1
        self.data[0] = 0xA1

        self.subcommand_is_set = False

        self.is_writing = None

    def clear_sub_command(self):
        for i in range(14, 51):
            self.data[i] = 0x00
        self.subcommand_is_set = False

    def set_input_report_id(self, _id):
        """
        :param _id: e.g. 0x21 Standard input reports used for sub command replies
                         etc... (TODO)
        """
        self.data[1] = _id

    def set_timer(self, timer):
        """
        Input report timer (0x00-0xFF), usually set by the transport
        """
        self.data[2] = timer % 256

    def set_misc(self):
        # battery level + connection info
        self.data[3] = 0x8E

    def set_button_status(self, button_status: ButtonState):
        """
        Sets the button status bytes
        """
        self.data[4:7] = iter(button_status)

    def set_left_analog_stick(self):
        """
        TODO
        """
        self.data[7:10] = [0x01, 0x18, 0x80]

    def set_right_analog_stick(self):
        """
        TODO
        """
        self.data[10:13] = [0x01, 0x18, 0x80]

    def set_vibrator_input(self):
        """
        TODO
        """
        self.data[13] = 0x80

    def set_ack(self, ack):
        """
        ACK byte for subcmd reply
        TODO
        """
        self.data[14] = ack

    def sub_0x02_device_info(self, mac, fm_version=(0x03, 0x48), controller=Controller.JOYCON_L):
        """
        Sub command 0x02 request device info response.

        :param mac: Controller MAC address in Big Endian (6 Bytes)
        :param fm_version: TODO
        :param controller: 1=Left Joy-Con, 2=Right Joy-Con, 3=Pro Controller
        """
        if len(fm_version) != 2:
            raise ValueError('Firmware version must consist of 2 bytes!')
        elif len(mac) != 6:
            raise ValueError('Bluetooth mac address must consist of 6 bytes!')

        self.reply_to_subcommand_id(0x02)

        # sub command reply data
        offset = 16
        self.data[offset: offset + 2] = fm_version
        self.data[offset + 2] = controller.value
        self.data[offset + 3] = 0x02
        self.data[offset + 4: offset + 10] = mac
        self.data[offset + 10] = 0x01
        self.data[offset + 11] = 0x01

    def reply_to_subcommand_id(self, id_):
        self.subcommand_is_set = True
        self.data[15] = id_

    def sub_0x08_shipment(self):
        self.reply_to_subcommand_id(0x08)

    def sub_0x10_spi_flash_read(self, output_report):
        self.reply_to_subcommand_id(0x10)
        self.data[16:18] = output_report.data[12:14]

    def sub_0x03_set_input_report_mode(self):
        self.reply_to_subcommand_id(0x03)

    def sub_0x04_trigger_buttons_elapsed_time(self):
        self.reply_to_subcommand_id(0x04)

        # TODO
        blub = [0x00, 0xCC, 0x00, 0xEE, 0x00, 0xFF]
        self.data[16:22] = blub

    async def write(self, transport):
        if self.is_writing is None:
            self.is_writing = asyncio.ensure_future(transport.write(self))
        await self.is_writing
        self.is_writing = None

    def __bytes__(self):
        if self.subcommand_is_set:
            return bytes(self.data)
        else:
            return bytes(self.data[:15])


class SubCommand(Enum):
    REQUEST_DEVICE_INFO = 0x02
    SET_INPUT_REPORT_MODE = 0x03
    TRIGGER_BUTTONS_ELAPSED_TIME = 0x04
    SET_SHIPMENT_STATE = 0x08
    SPI_FLASH_READ = 0x10
    ENABLE_6AXIS_SENSOR = 0x40
    NOT_IMPLEMENTED = 0xFF


class OutputReport:
    def __init__(self, data):
        if data[0] != 0xA2:
            raise ValueError('Output reports must start with 0xA2')
        self.data = data

    def get_sub_command(self):
        if len(self.data) < 12:
            return None, None
        try:
            return self.data[11], SubCommand(self.data[11])
        except ValueError:
            return self.data[11], SubCommand.NOT_IMPLEMENTED

    def __bytes__(self):
        return bytes(self.data)
