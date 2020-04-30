import enum


class Controller(enum.Enum):
    JOYCON_L = 0x01
    JOYCON_R = 0x02
    PRO_CONTROLLER = 0x03

    def device_name(self):
        """
        :returns corresponding bluetooth device name
        """
        if self == Controller.JOYCON_L:
            return 'Joy-Con (L)'
        elif self == Controller.JOYCON_R:
            return 'Joy-Con (R)'
        elif self == Controller.PRO_CONTROLLER:
            return 'Pro Controller'
        else:
            raise NotImplementedError()

    @staticmethod
    def from_arg(arg):
        if arg == 'JOYCON_R':
            return Controller.JOYCON_R
        elif arg == 'JOYCON_L':
            return Controller.JOYCON_L
        elif arg == 'PRO_CONTROLLER':
            return Controller.PRO_CONTROLLER
        else:
            raise ValueError(f'Unknown controller "{arg}".')
