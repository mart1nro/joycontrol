from enum import Enum, auto

#[0xA1 0, 0x21 1, 0x05 2, 0x8E 3,
# 0x84, 0x00, 0x12, button
# 0x01, 0x18, 0x80, left analog
# 0x01, 0x18, 0x80, right analog
# 0x80, vibrator?
# 0x82, 0x02, 0x03, 0x48, 0x01, 0x02, 0xDC, 0xA6, 0x32, 0x71, 0x58, 0xBB, 0x01, 0x01]
from controller import Controller


class InputReport:
    def __init__(self):
        self.data = [0x00] * 50
        # all input reports are prepended with 0xA1
        self.data[0] = 0xA1

    def set_input_report_id(self, _id):
        """
        :param _id: e.g. 0x21 Standard input reports used for subcommand replies, etc... (TODO)
        """
        self.data[1] = _id

    def set_timer(self, timer):
        """
        Input report timer, usually set by the transport
        """
        self.data[2] = timer % 256

    def set_misc(self):
        # battery level + connection info
        self.data[3] = 0x8E

        # ACK byte for subcmd reply
        self.data[14] = 0x82

    def set_button_status(self):
        """
        TODO
        """
        self.data[4:7] = [0x84, 0x00, 0x12]

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

    def sub_0x2_device_info(self, mac, fm_version=(0x03, 0x48), controller=Controller.JOYCON_L):
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

        # reply to sub command ID
        self.data[15] = 0x02

        # sub command reply data
        offset = 16
        self.data[offset: offset + 2] = fm_version
        self.data[offset + 2] = controller.value
        self.data[offset + 3] = 0x02
        self.data[offset + 4: offset + 10] = mac
        self.data[offset + 10] = 0x01
        self.data[offset + 11] = 0x01

    def __bytes__(self):
        return bytes(self.data)


class SubCommand(Enum):
    REQUEST_DEVICE_INFO = auto()
    NOT_IMPLEMENTED = auto()


class OutputReport:
    def __init__(self, data):
        if data[0] != 0xA2:
            raise ValueError('Output reports must start with 0xA2')
        self.data = data

    def get_sub_command(self):
        print('subcommand:', self.data[11])
        if self.data[11] == 0x02:
            return SubCommand.REQUEST_DEVICE_INFO
        else:
            return None

    def __bytes__(self):
        return bytes(self.data)
