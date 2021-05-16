import asyncio

from joycontrol import utils
from joycontrol.controller import Controller
from joycontrol.memory import FlashMemory


class ControllerState:
    def __init__(self, protocol, controller: Controller, spi_flash: FlashMemory = None):
        self._protocol = protocol
        self._controller = controller
        self._nfc_content = None

        self._spi_flash = spi_flash

        self.button_state = ButtonState(controller)

        # create left stick state
        self.l_stick_state = self.r_stick_state = None
        if controller in (Controller.PRO_CONTROLLER, Controller.JOYCON_L):
            # load calibration data from memory
            calibration = None
            if spi_flash is not None:
                calibration_data = spi_flash.get_user_l_stick_calibration()
                if calibration_data is None:
                    calibration_data = spi_flash.get_factory_l_stick_calibration()
                calibration = LeftStickCalibration.from_bytes(calibration_data)

            self.l_stick_state = StickState(calibration=calibration)
            if calibration is not None:
                self.l_stick_state.set_center()

        # create right stick state
        if controller in (Controller.PRO_CONTROLLER, Controller.JOYCON_R):
            # load calibration data from memory
            calibration = None
            if spi_flash is not None:
                calibration_data = spi_flash.get_user_r_stick_calibration()
                if calibration_data is None:
                    calibration_data = spi_flash.get_factory_r_stick_calibration()
                calibration = RightStickCalibration.from_bytes(calibration_data)

            self.r_stick_state = StickState(calibration=calibration)
            if calibration is not None:
                self.r_stick_state.set_center()

        self.sig_is_send = asyncio.Event()

    def get_controller(self):
        return self._controller

    def get_flash_memory(self):
        return self._spi_flash

    def set_nfc(self, nfc_content):
        self._nfc_content = nfc_content

    def get_nfc(self):
        return self._nfc_content

    async def send(self):
        """
        Invokes protocol.send_controller_state(). Returns after the controller state was send.
        Raises NotConnected exception if the connection was lost.
        """
        await self._protocol.send_controller_state()

    async def connect(self):
        """
        Waits until the switch is paired with the controller and accepts button commands
        """
        await self._protocol.sig_input_ready.wait()


class ButtonState:
    """
    Utility class to set buttons in the input report
    https://github.com/dekuNukem/Nintendo_Switch_Reverse_Engineering/blob/master/bluetooth_hid_notes.md
    Byte 	0 	    1 	    2 	    3 	    4 	    5 	    6 	    7
    1   	Y 	    X 	    B 	    A 	    SR 	    SL 	    R 	    ZR
    2       Minus 	Plus 	R Stick L Stick Home 	Capture
    3       Down 	Up 	    Right 	Left 	SR 	    SL 	    L 	    ZL

    Example for generated methods: home button (byte_2, 4)

    def home(self, pushed=True):
        if pushed != utils.get_bit(self.byte_2, 4):
            self.byte_2 = utils.flip_bit(self.byte_2, 4)

    def home_is_set(self):
        return get_bit(self.byte_2, 4)
    """
    def __init__(self, controller: Controller):
        self.controller = controller

        # 3 bytes
        self._byte_1 = 0
        self._byte_2 = 0
        self._byte_3 = 0

        # generating methods for each button
        def button_method_factory(byte, bit):
            def setter(pushed=True):
                _byte = getattr(self, byte)

                if pushed != utils.get_bit(_byte, bit):
                    setattr(self, byte, utils.flip_bit(_byte, bit))

            def getter():
                return utils.get_bit(getattr(self, byte), bit)
            return setter, getter

        if self.controller == Controller.PRO_CONTROLLER:
            self._available_buttons = {'y', 'x', 'b', 'a', 'r', 'zr',
                                       'minus', 'plus', 'r_stick', 'l_stick', 'home', 'capture',
                                       'down', 'up', 'right', 'left', 'l', 'zl'}
        elif self.controller == Controller.JOYCON_R:
            self._available_buttons = {'y', 'x', 'b', 'a', 'sr', 'sl', 'r', 'zr',
                                       'plus', 'r_stick', 'home'}
        elif self.controller == Controller.JOYCON_L:
            self._available_buttons = {'minus', 'l_stick', 'capture',
                                       'down', 'up', 'right', 'left', 'sr', 'sl', 'l', 'zl'}

        # byte 1
        if self.controller == Controller.PRO_CONTROLLER or self.controller == Controller.JOYCON_R:
            self.y, self.y_is_set = button_method_factory('_byte_1', 0)
            self.x, self.x_is_set = button_method_factory('_byte_1', 1)
            self.b, self.b_is_set = button_method_factory('_byte_1', 2)
            self.a, self.a_is_set = button_method_factory('_byte_1', 3)

            if self.controller == Controller.JOYCON_R:
                self.sr, self.sr_is_set = button_method_factory('_byte_1', 4)
                self.sl, self.sl_is_set = button_method_factory('_byte_1', 5)

            self.r, self.r_is_set = button_method_factory('_byte_1', 6)
            self.zr, self.zr_is_set = button_method_factory('_byte_1', 7)

        # byte 2
        self.minus, self.minus_is_set = button_method_factory('_byte_2', 0)
        self.plus, self.plus_is_set = button_method_factory('_byte_2', 1)
        self.r_stick, self.r_stick_is_set = button_method_factory('_byte_2', 2)
        self.l_stick, self.l_stick_is_set = button_method_factory('_byte_2', 3)
        if self.controller == Controller.JOYCON_R or self.controller == Controller.PRO_CONTROLLER:
            self.home, self.home_is_set = button_method_factory('_byte_2', 4)
        if self.controller == Controller.JOYCON_L or self.controller == Controller.PRO_CONTROLLER:
            self.capture, self.capture_is_set = button_method_factory('_byte_2', 5)

        # byte 3
        if self.controller == Controller.PRO_CONTROLLER or self.controller == Controller.JOYCON_L:
            self.down, self.down_is_set = button_method_factory('_byte_3', 0)
            self.up, self.up_is_set = button_method_factory('_byte_3', 1)
            self.right, self.right_is_set = button_method_factory('_byte_3', 2)
            self.left, self.left_is_set = button_method_factory('_byte_3', 3)

            if self.controller == Controller.JOYCON_L:
                self.sr, self.sr_is_set = button_method_factory('_byte_3', 4)
                self.sl, self.sl_is_set = button_method_factory('_byte_3', 5)

            self.l, self.l_is_set = button_method_factory('_byte_3', 6)
            self.zl, self.zl_is_set = button_method_factory('_byte_3', 7)

    def set_button(self, button, pushed=True):
        button = button.lower()
        if button not in self._available_buttons:
            raise ValueError(f'Given button "{button}" is not available to {self.controller.device_name()}.')
        getattr(self, button)(pushed=pushed)

    def get_button(self, button):
        button = button.lower()
        if button not in self._available_buttons:
            raise ValueError(f'Given button "{button}" is not available to {self.controller.device_name()}.')
        return getattr(self, f'{button}_is_set')()

    def get_available_buttons(self):
        """
        :returns: set of valid buttons
        """
        return set(self._available_buttons)

    def __iter__(self):
        """
        :returns: iterator over the button bytes
        """
        yield self._byte_1
        yield self._byte_2
        yield self._byte_3

    def clear(self):
        self._byte_1 = self._byte_2 = self._byte_3 = 0

    def __bytes__(self):
        return bytes([self._byte_1, self._byte_2, self._byte_3])


async def button_press(controller_state, *buttons):
    """
    Set given buttons in the controller state to the pressed down state and wait till send.
    :param controller_state:
    :param buttons: Buttons to press down (see ButtonState.get_available_buttons)
    """
    if not buttons:
        raise ValueError('No Buttons were given.')

    button_state = controller_state.button_state

    for button in buttons:
        # push button
        button_state.set_button(button, pushed=True)

    # wait until report is send
    await controller_state.send()


async def button_release(controller_state, *buttons):
    """
    Set given buttons in the controller state to the unpressed state and wait till send.
    :param controller_state:
    :param buttons: Buttons to set to unpressed (see ButtonState.get_available_buttons)
    """
    if not buttons:
        raise ValueError('No Buttons were given.')

    button_state = controller_state.button_state

    for button in buttons:
        # release button
        button_state.set_button(button, pushed=False)

    # wait until report is send
    await controller_state.send()


async def button_push(controller_state, *buttons, sec=0.1):
    """
    Shortly push the given buttons. Wait until the controller state is send.
    :param controller_state:
    :param buttons: Buttons to push (see ButtonState.get_available_buttons)
    :param sec: Seconds to wait before releasing the button, default: 0.1
    """
    await button_press(controller_state, *buttons)
    await asyncio.sleep(sec)
    await button_release(controller_state, *buttons)


class _StickCalibration:
    def __init__(self, h_center, v_center, h_max_above_center, v_max_above_center, h_max_below_center, v_max_below_center):
        self.h_center = h_center
        self.v_center = v_center

        self.h_max_above_center = h_max_above_center
        self.v_max_above_center = v_max_above_center
        self.h_max_below_center = h_max_below_center
        self.v_max_below_center = v_max_below_center

    def __str__(self):
        return f'h_center:{self.h_center} v_center:{self.v_center} h_max_above_center:{self.h_max_above_center} ' \
               f'v_max_above_center:{self.v_max_above_center} h_max_below_center:{self.h_max_below_center} ' \
               f'v_max_below_center:{self.v_max_below_center}'


class LeftStickCalibration(_StickCalibration):
    @staticmethod
    def from_bytes(_9bytes):
        h_max_above_center = (_9bytes[1] << 8) & 0xF00 | _9bytes[0]
        v_max_above_center = (_9bytes[2] << 4) | (_9bytes[1] >> 4)
        h_center =           (_9bytes[4] << 8) & 0xF00 | _9bytes[3]
        v_center =           (_9bytes[5] << 4) | (_9bytes[4] >> 4)
        h_max_below_center = (_9bytes[7] << 8) & 0xF00 | _9bytes[6]
        v_max_below_center = (_9bytes[8] << 4) | (_9bytes[7] >> 4)

        return _StickCalibration(h_center, v_center, h_max_above_center, v_max_above_center,
                                 h_max_below_center, v_max_below_center)


class RightStickCalibration(_StickCalibration):
    @staticmethod
    def from_bytes(_9bytes):
        h_center =           (_9bytes[1] << 8) & 0xF00 | _9bytes[0]
        v_center =           (_9bytes[2] << 4) | (_9bytes[1] >> 4)
        h_max_below_center = (_9bytes[4] << 8) & 0xF00 | _9bytes[3]
        v_max_below_center = (_9bytes[5] << 4) | (_9bytes[4] >> 4)
        h_max_above_center = (_9bytes[7] << 8) & 0xF00 | _9bytes[6]
        v_max_above_center = (_9bytes[8] << 4) | (_9bytes[7] >> 4)

        return _StickCalibration(h_center, v_center, h_max_above_center, v_max_above_center,
                                 h_max_below_center, v_max_below_center)


class StickState:
    def __init__(self, h=0, v=0, calibration: _StickCalibration = None):
        for val in (h, v):
            if not 0 <= val < 0x1000:
                raise ValueError(f'Stick values must be in [0,{0x1000})')

        self._h_stick = h
        self._v_stick = v

        self._calibration = calibration

    def set_h(self, value):
        if not 0 <= value < 0x1000:
            raise ValueError(f'Stick values must be in [0,{0x1000})')
        self._h_stick = value

    def get_h(self):
        return self._h_stick

    def set_v(self, value):
        if not 0 <= value < 0x1000:
            raise ValueError(f'Stick values must be in [0,{0x1000})')
        self._v_stick = value

    def get_v(self):
        return self._v_stick

    def set_center(self):
        """
        Sets stick to center position using the calibration data.
        """
        if self._calibration is None:
            raise ValueError('No calibration data available.')
        self._h_stick = self._calibration.h_center
        self._v_stick = self._calibration.v_center

    def is_center(self, radius=0):
        return self._calibration.h_center - radius <= self._h_stick <= self._calibration.h_center + radius and \
               self._calibration.v_center - radius <= self._v_stick <= self._calibration.v_center + radius

    def set_up(self):
        """
        Sets stick to up position using the calibration data.
        """
        if self._calibration is None:
            raise ValueError('No calibration data available.')
        self._h_stick = self._calibration.h_center
        self._v_stick = self._calibration.v_center + self._calibration.v_max_above_center

    def set_down(self):
        """
        Sets stick to down position using the calibration data.
        """
        if self._calibration is None:
            raise ValueError('No calibration data available.')
        self._h_stick = self._calibration.h_center
        self._v_stick = self._calibration.v_center - self._calibration.v_max_below_center

    def set_left(self):
        """
        Sets stick to left position using the calibration data.
        """
        if self._calibration is None:
            raise ValueError('No calibration data available.')
        self._h_stick = self._calibration.h_center - self._calibration.h_max_below_center
        self._v_stick = self._calibration.v_center

    def set_right(self):
        """
        Sets stick to right position using the calibration data.
        """
        if self._calibration is None:
            raise ValueError('No calibration data available.')
        self._h_stick = self._calibration.h_center + self._calibration.h_max_above_center
        self._v_stick = self._calibration.v_center

    def set_calibration(self, calibration):
        self._calibration = calibration

    def get_calibration(self):
        if self._calibration is None:
            raise ValueError('No calibration data available.')
        return self._calibration

    @staticmethod
    def from_bytes(_3bytes):
        stick_h = _3bytes[0] | ((_3bytes[1] & 0xF) << 8)
        stick_v = (_3bytes[1] >> 4) | (_3bytes[2] << 4)

        return StickState(h=stick_h, v=stick_v)

    def __bytes__(self):
        byte_1 = 0xFF & self._h_stick
        byte_2 = (self._h_stick >> 8) | ((0xF & self._v_stick) << 4)
        byte_3 = self._v_stick >> 4
        assert all(0 <= byte <= 0xFF for byte in (byte_1, byte_2, byte_3))
        return bytes((byte_1, byte_2, byte_3))
