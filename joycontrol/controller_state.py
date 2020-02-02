import asyncio

from joycontrol.button_state import ButtonState
from joycontrol.protocol import ControllerProtocol


class ControllerState:
    def __init__(self, transport: asyncio.Transport, protocol: ControllerProtocol):
        super().__init__()
        self.transport = transport
        self.protocol = protocol

        self.input_report = self.protocol.get_button_input_report()

    async def send(self):
        await self.input_report.write(self.transport)

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
        self.input_report.set_button_status(button_state)

    def set_stick_state(self):
        """
        TODO
        """
        raise NotImplementedError()


async def button_push(controller_state, button, sec=0.1):
    button_state = ButtonState()

    # push button
    getattr(button_state, button)()

    # send report
    controller_state.set_button_state(button_state)
    await controller_state.send()
    await asyncio.sleep(sec)

    # release button
    getattr(button_state, button)()

    # send report
    controller_state.set_button_state(button_state)
    await controller_state.send()