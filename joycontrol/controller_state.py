import asyncio

from joycontrol import utils


class ControllerState:
    def __init__(self, protocol):
        self._protocol = protocol

        self.button_state = None
        self.stick_state = None

        self.sig_is_send = asyncio.Event()

    async def send(self):
        self.sig_is_send.clear()
        await self.sig_is_send.wait()

    async def connect(self):
        """
        Waits until the switch is paired with the controller and accepts button commands
        """
        await self._protocol.sig_wait_player_lights.wait()


class ButtonState:
    """
    Utility class to set buttons in the input report
    https://github.com/dekuNukem/Nintendo_Switch_Reverse_Engineering/blob/master/bluetooth_hid_notes.md
    Byte 	0 	    1 	    2 	    3 	    4 	    5 	    6 	    7
    1   	Y 	    X 	    B 	    A 	    SR 	    SL 	    R 	    ZR
    2       Minus 	Plus 	R Stick L Stick Home 	Capture
    3       Down 	Up 	    Right 	Left 	SR 	    SL 	    L 	    ZL
    """
    def __init__(self):
        # 3 bytes
        self._byte_1 = 0
        self._byte_2 = 0
        self._byte_3 = 0

        # generating methods for each button
        def button_method_factory(byte, bit):
            def flip():
                setattr(self, byte, utils.flip_bit(getattr(self, byte), bit))

            def getter():
                return utils.get_bit(getattr(self, byte), bit)
            return flip, getter

        # byte 1
        self.y, self.y_is_set = button_method_factory('_byte_1', 0)
        self.x, self.x_is_set = button_method_factory('_byte_1', 1)
        self.b, self.b_is_set = button_method_factory('_byte_1', 2)
        self.a, self.a_is_set = button_method_factory('_byte_1', 3)
        self.right_sr, self.right_sr_is_set = button_method_factory('_byte_1', 4)
        self.right_sl, self.right_sl_is_set = button_method_factory('_byte_1', 5)
        self.r, self.r_is_set = button_method_factory('_byte_1', 6)
        self.zr, self.zr_is_set = button_method_factory('_byte_1', 7)

        # byte 2
        self.minus, self.minus_is_set = button_method_factory('_byte_2', 0)
        self.plus, self.plus_is_set = button_method_factory('_byte_2', 1)
        self.r_stick, self.r_stick_is_set = button_method_factory('_byte_2', 2)
        self.l_stick, self.l_stick_is_set = button_method_factory('_byte_2', 3)
        self.home, self.home_is_set = button_method_factory('_byte_2', 4)
        self.capture, self.capture_is_set = button_method_factory('_byte_2', 5)

        # byte 3
        self.down, self.down_is_set = button_method_factory('_byte_3', 0)
        self.up, self.up_is_set = button_method_factory('_byte_3', 1)
        self.right, self.right_is_set = button_method_factory('_byte_3', 2)
        self.left, self.left_is_set = button_method_factory('_byte_3', 3)
        self.left_sr, self.left_sr_is_set = button_method_factory('_byte_3', 4)
        self.left_sl, self.left_sl_is_set = button_method_factory('_byte_3', 5)
        self.l, self.l_is_set = button_method_factory('_byte_3', 6)
        self.zl, self.zl_is_set = button_method_factory('_byte_3', 7)

    """
    Example for generated methods: home button (byte_2, 4)

    def home(self):
        self.byte_2 = flip_bit(self.byte_2, 4)

    def home_is_set(self):
        return get_bit(self.byte_2, 4)
    """

    def __iter__(self):
        """
        @returns iterator of the button bytes
        """
        yield self._byte_1
        yield self._byte_2
        yield self._byte_3

    def clear(self):
        self._byte_1 = self._byte_2 = self._byte_3 = 0


async def button_push(controller_state, button, sec=0.1):
    button_state = ButtonState()

    # push button
    getattr(button_state, button)()

    # send report
    controller_state.button_state = button_state
    await controller_state.send()
    await asyncio.sleep(sec)

    # release button
    getattr(button_state, button)()

    # send report
    controller_state.button_state = button_state
    await controller_state.send()


class StickState:
    def __init__(self):
        raise NotImplementedError()
