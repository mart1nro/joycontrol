import asyncio

from joycontrol.button_state import ButtonState
from joycontrol.protocol import ControllerProtocol


class ControllerState:
    def __init__(self, transport: asyncio.Transport, protocol: ControllerProtocol):
        super().__init__()
        self.transport = transport

        self.protocol = protocol

    async def send(self):
        await self.protocol.button_input_report.write(self.transport)

    async def connect(self):
        """
        Waits until the switch is paired with the controller and accepts button commands
        """
        # TODO HACK: Hard to say for now.
        await self.protocol.wait_for_output_report()
        # The switch sends data to our device, it shouldn't take long until the connection is fully established.
        await asyncio.sleep(5)

    def set_button_state(self, button_state: ButtonState):
        """
        Sets the button status bytes in the input report
        """
        self.protocol.button_input_report.set_button_status(button_state)

    def set_stick_state(self):
        """
        TODO
        """
        raise NotImplementedError()


