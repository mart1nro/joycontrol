import asyncio
import enum
import logging
import socket
from asyncio import BaseTransport, BaseProtocol
from typing import Optional, Union, Tuple, Text

import logging_default as log
import utils
from device import HidDevice
from transport import L2CAP_Transport

logger = logging.getLogger(__name__)


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


def controller_protocol_factory(controller: Controller):
    def create_controller_protocol():
        return ControllerProtocol(controller)
    return create_controller_protocol


class ControllerProtocol(BaseProtocol):
    def __init__(self, controller: Controller):
        self.transport = None

    def connection_made(self, transport: BaseTransport) -> None:
        logger.debug('Connection established.')
        self.transport = transport

    def connection_lost(self, exc: Optional[Exception]) -> None:
        raise NotImplementedError()

    async def report_received(self, data: Union[bytes, Text], addr: Tuple[str, int]) -> None:
        raise NotImplementedError()

    def error_received(self, exc: Exception) -> None:
        raise NotImplementedError()
