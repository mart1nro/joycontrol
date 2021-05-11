from enum import Enum

from joycontrol.controller import Controller


class InputReport:
    """
    Class to create Input Reports. Reference:
    https://github.com/dekuNukem/Nintendo_Switch_Reverse_Engineering/blob/master/bluetooth_hid_notes.md
    """
    def __init__(self, data=None):
        if not data:
            self.data = [0x00] * 363
            # all input reports are prepended with 0xA1
            self.data[0] = 0xA1
        else:
            if data[0] != 0xA1:
                raise ValueError('Input reports must start with 0xA1')
            self.data = data

    def clear_sub_command(self):
        """
        Clear sub command reply data of 0x21 input reports
        """
        for i in range(14, 51):
            self.data[i] = 0x00

    def get_stick_data(self):
        # TODO: Not every input report has stick data
        return self.data[7:13]

    def get_sub_command_reply_data(self):
        if len(self.data) < 50:
            raise ValueError('Not enough data')

        return self.data[16:51]

    def set_input_report_id(self, _id):
        """
        :param _id: e.g. 0x21 Standard input reports used for sub command replies
                         0x30 Input reports with IMU data instead of sub command replies
                         etc... (TODO)
        """
        self.data[1] = _id

    def get_input_report_id(self):
        return self.data[1]

    def set_timer(self, timer):
        """
        Input report timer [0x00-0xFF], usually set by the transport
        """
        self.data[2] = timer % 256

    def set_misc(self):
        # battery level + connection info
        self.data[3] = 0x8E

    def set_button_status(self, button_status):
        """
        Sets the button status bytes
        """
        self.data[4:7] = iter(button_status)

    def set_stick_status(self, left_stick, right_stick):
        """
        Sets the joystick status bytes
        """
        self.set_left_analog_stick(bytes(left_stick) if left_stick else bytes(3))
        self.set_right_analog_stick(bytes(right_stick) if right_stick else bytes(3))

    def set_left_analog_stick(self, left_stick_bytes):
        """
        Set left analog stick status bytes.
        :param left_stick_bytes: 3 bytes
        """
        if len(left_stick_bytes) != 3:
            raise ValueError('Left stick status data must be exactly 3 bytes!')
        self.data[7:10] = left_stick_bytes

    def set_right_analog_stick(self, right_stick_bytes):
        """
        Set right analog stick status bytes.
        :param right_stick_bytes: 3 bytes
        """
        if len(right_stick_bytes) != 3:
            raise ValueError('Right stick status data must be exactly 3 bytes!')
        self.data[10:13] = right_stick_bytes

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

    def get_ack(self):
        return self.data[14]

    def set_6axis_data(self):
        """
        Set accelerator and gyro of 0x30 input reports
        TODO
        """
        # HACK: Set all 0 for now
        for i in range(14, 50):
            self.data[i] = 0x00

    def set_ir_nfc_data(self, data):
        if len(data) > 313:
            raise ValueError(f'Too much data {len(data)} > 313.')
        elif len(data) != 313:
            print("warning : too short mcu data")
        self.data[50:50+len(data)] = data

    def reply_to_subcommand_id(self, _id):
        if isinstance(_id, SubCommand):
            self.data[15] = _id.value
        else:
            self.data[15] = _id

    def get_reply_to_subcommand_id(self):
        if len(self.data) < 16:
            return None
        try:
            return SubCommand(self.data[15])
        except ValueError:
            raise NotImplementedError(f'Sub command id {hex(self.data[11])} not implemented')

    def sub_0x02_device_info(self, mac, fm_version=(0x04, 0x00), controller=Controller.JOYCON_L):
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

    def sub_0x10_spi_flash_read(self, offset, size, data):
        if len(data) != size:
            raise ValueError(f'Length of data {len(data)} does not match size {size}')
        if size > 0x1D:
            raise ValueError(f'Size can not exceed {0x1D}')

        self.reply_to_subcommand_id(0x10)

        # write offset to data
        for i in range(16, 16 + 4):
            self.data[i] = offset % 0x100
            offset = offset // 0x100

        self.data[20] = size
        self.data[21:21+len(data)] = data

    def sub_0x04_trigger_buttons_elapsed_time(self, L_ms=0, R_ms=0, ZL_ms=0, ZR_ms=0, SL_ms=0, SR_ms=0, HOME_ms=0):
        """
        Set sub command data for 0x04 reply. Arguments are in ms and must be divisible by 10.
        """
        if any(ms > 10*0xffff for ms in (L_ms, R_ms, ZL_ms, ZR_ms, SL_ms, SR_ms, HOME_ms)):
            raise ValueError(f'Values can not exceed {10*0xffff} ms.')

        def set(offset, ms):
            # reply data offset
            sub_command_offset = 16
            value = int(ms // 10)
            self.data[sub_command_offset + offset] = 0xff & value
            self.data[sub_command_offset + offset + 1] = (0xff00 & value) >> 8

        set(0, L_ms)
        set(2, R_ms)
        set(4, ZL_ms)
        set(6, ZR_ms)
        set(8, SL_ms)
        set(10, SR_ms)
        set(12, HOME_ms)

    def __bytes__(self):
        _id = self.get_input_report_id()
        if _id == 0x21:
            return bytes(self.data[:51])
        elif _id == 0x30:
            return bytes(self.data[:14])
        elif _id == 0x31:
            return bytes(self.data[:363])
        else:
            return bytes(self.data[:51])

    def __str__(self):
        _id = f'Input {self.get_input_report_id():x}'
        _info = ''
        if self.get_input_report_id() == 0x21:
            _info = self.get_reply_to_subcommand_id()
        _bytes = ' '.join(f'{byte:x}' for byte in bytes(self))

        return f'{_id} {_info}\n{_bytes}'


class SubCommand(Enum):
    REQUEST_DEVICE_INFO = 0x02
    SET_INPUT_REPORT_MODE = 0x03
    TRIGGER_BUTTONS_ELAPSED_TIME = 0x04
    SET_SHIPMENT_STATE = 0x08
    SPI_FLASH_READ = 0x10
    SET_NFC_IR_MCU_CONFIG = 0x21
    SET_NFC_IR_MCU_STATE = 0x22
    SET_PLAYER_LIGHTS = 0x30
    ENABLE_6AXIS_SENSOR = 0x40
    ENABLE_VIBRATION = 0x48


class OutputReportID(Enum):
    SUB_COMMAND = 0x01
    RUMBLE_ONLY = 0x10
    REQUEST_IR_NFC_MCU = 0x11


class OutputReport:
    def __init__(self, data=None):
        if not data:
            data = 50 * [0x00]
            data[0] = 0xA2
        elif data[0] != 0xA2:
            raise ValueError('Output reports must start with a 0xA2 byte!')
        self.data = data

    def get_output_report_id(self):
        try:
            return OutputReportID(self.data[1])
        except ValueError:
            raise NotImplementedError(f'Output report id {hex(self.data[1])} not implemented')

    def set_output_report_id(self, _id):
        if isinstance(_id, OutputReportID):
            self.data[1] = _id.value
        else:
            self.data[1] = _id

    def get_timer(self):
        return OutputReportID(self.data[2])

    def set_timer(self, timer):
        """
        Output report timer in [0x0, 0xF]
        """
        self.data[2] = timer % 0x10

    def get_rumble_data(self):
        return self.data[3:11]

    def get_sub_command(self):
        if len(self.data) < 12:
            return None
        try:
            return SubCommand(self.data[11])
        except ValueError:
            raise NotImplementedError(f'Sub command id {hex(self.data[11])} not implemented')

    def set_sub_command(self, _id):
        if isinstance(_id, SubCommand):
            self.data[11] = _id.value
        elif isinstance(_id, int):
            self.data[11] = _id
        else:
            raise ValueError('id must be int or SubCommand')

    def get_sub_command_data(self):
        if len(self.data) < 13:
            return None
        return self.data[12:]

    def set_sub_command_data(self, data):
        for i, _byte in enumerate(data):
            self.data[12+i] = _byte

    def sub_0x10_spi_flash_read(self, offset, size):
        """
        Creates output report data with spi flash read sub command.
        :param offset: start byte of the spi flash to read in [0x00, 0x80000)
        :param size: size of data to be read in [0x00, 0x1D]
        """
        if size > 0x1D:
            raise ValueError(f'Size read can not exceed {0x1D}')
        if offset+size > 0x80000:
            raise ValueError(f'Given address range exceeds max address {0x80000-1}')

        self.set_output_report_id(OutputReportID.SUB_COMMAND)
        self.set_sub_command(SubCommand.SPI_FLASH_READ)

        # write offset to data
        for i in range(12, 12+4):
            self.data[i] = offset % 0x100
            offset = offset // 0x100

        self.data[16] = size

    def __bytes__(self):
        return bytes(self.data)

    def __str__(self):
        _id = f'Output {self.get_output_report_id()}'
        _info = ''
        if self.get_output_report_id() == OutputReportID.SUB_COMMAND:
            _info = self.get_sub_command()
        _bytes = ' '.join(f'{byte:x}' for byte in bytes(self))

        return f'{_id} {_info}\n{_bytes}'
