import enum
import logging
import crc8
import traceback

from joycontrol.controller_state import ControllerState

logger = logging.getLogger(__name__)

def debug(args):
    print(args)
    return args

###############################################################
## This simulates the MCU in the right joycon/Pro-Controller ##
###############################################################
# This is sufficient to read one amiibo
# multiple can mess up the internal state
# anything but amiboo is not supported
# TODO:
#     - figure out the NFC-content transfer, currently everything is hardcoded to work wich amiibo
#       see https://github.com/CTCaer/jc_toolkit/blob/5.2.0/jctool/jctool.cpp l2456ff for sugesstions
#     - IR-camera
#     - writing to Amiibo

# These Values are used in set_power, set_config and get_status packets
# But not all of them can appear in every one
# see https://github.com/CTCaer/jc_toolkit/blob/5.2.0/jctool/jctool.cpp l 2359 for set_config
class MCUPowerState(enum.Enum):
    SUSPENDED = 0x00 # set_power
    READY = 0x01 # set_power, set_config, get_status
    READY_UPDATE = 0x02
    CONFIGURED_NFC = 0x04 # set_config, get_status
    # CONFIGURED_IR = 0x05  # TODO: support this
    # CONFIGUERED_UPDATE = 0x06

SET_POWER_VALUES = (
    MCUPowerState.SUSPENDED.value,
    MCUPowerState.READY.value,
#   MCUPowerState.READY_UPDATE.value,
)

SET_CONFIG_VALUES = (
    MCUPowerState.READY.value,
    MCUPowerState.CONFIGURED_NFC.value,
#   MCUPowerState.CONFIGURED_IR.value,
)

GET_STATUS_VALUES = (
    MCUPowerState.READY.value,
#   MCUPowerState.READY_UPDATE.value,
    MCUPowerState.CONFIGURED_NFC.value,
#   MCUPowerState.CONFIGURED_IR.value
)


def MCU_crc(data):
    if not isinstance(data, bytes):
        data = bytes(data)
    my_hash = crc8.crc8()
    my_hash.update(data)
    # At this point I'm not even mad this works...
    return my_hash.digest()[0]


class NFC_state(enum.Enum):
    NONE = 0x00
    POLL = 0x01
    PENDING_READ = 0x02
    POLL_AGAIN = 0x09


class MCU_Message:
    def __init__(self, *args, background=0, checksum=MCU_crc):
        self.data = bytearray([background] * 313)
        c = 0
        for i in args:
            if isinstance(i, str):
                b = bytes.fromhex(i)
            else:
                b = bytes(i)
            self.data[c:c+len(b)] = b
        if checksum:
            self.data[-1] = checksum(self.data[0:-1])

    def __bytes__(self):
        return self.data

class MarvelCinematicUniverse:
    def __init__(self, controller: ControllerState):

        self.power_state = MCUPowerState.SUSPENDED

        # NOT USED
        # Just a store for the remaining configuration data
        self.configuration = None

        # a cache to store the tag's data between Poll and Read
        self.nfc_tag_data = None
        self.nfc_state = NFC_state.NONE

        # NOT IMPLEMENTED
        # remove the tag from the controller after a successfull read
        self.remove_nfc_after_read = False

        # controllerstate to look for nfc-data
        self._controller = controller

        # We are getting 0x11 commands to do something, but cannot answer directly
        # responses have to be passed in regular input reports
        # If there was no Command, this is the default report
        self.no_response = [0] * 313
        self.no_response[0] = 0xff
        self.no_response[-1] = MCU_crc(self.no_response[:-1])
        self.response_queue = []
        self.max_response_queue_len = 3

        #debug
        self.reading = 0

    def _flush_response_queue(self):
        self.response_queue = []

    def _queue_response(self, resp):
        if resp == None: # the if "missing return statement" because python
            traceback.print_stack()
            exit(1)
        if len(self.response_queue) <= self.max_response_queue_len:
            self.response_queue.append(resp)

    def _force_queue_response(self, resp):
        self.response_queue.append(resp)

    def set_remove_nfc_after_read(self, value):
        self.remove_nfc_after_read = value

    def set_nfc_tag_data(self, data):
        logger.info("MCU-NFC: set NFC tag data")
        if not data:
            self.nfc_tag_data = None
        if not data is bytes:
            data = bytes(data)
        if len(data) != 540:
            logger.warning("not implemented length")
            return
        self.nfc_tag_data = data

    def entered_31_input_mode(self):
        resp = [0] * 313
        resp[0:8] = bytes.fromhex("0100000008001b01")
        resp[-1] = MCU_crc(resp[:-1])
        self._queue_response(resp)

    def _get_status_data(self, args=None):
        """
        create a status packet to be used when responding to 1101 commands
        """
        if self.power_state == MCUPowerState.SUSPENDED:
            logger.warning("MCU: status request when disabled")
            return self.no_response
        elif self.power_state.value in GET_STATUS_VALUES:
            resp = [0] * 313
            resp[0:7] = bytes.fromhex("0100000008001b")
            resp[7] = self.power_state.value
            resp[-1] = MCU_crc(resp[:-1])
            return resp
            #self._queue_response(resp)
            #return self._get_status_data()
        #else:
            #out = [0] * 313
            #out[0:7] = bytes.fromhex("01000000030005")
            #out[7] = MCUPowerState.READY.value
            #out[-1] = MCU_crc(out[0:-1])
            #return out

    def _get_nfc_status_data(self, args):
        out = [0] * 313
        out[0:7] = bytes.fromhex("2a000500000931")
        out[7] = self.nfc_state.value
        if self.nfc_state == NFC_state.POLL and self._controller.get_nfc():
            self.set_nfc_tag_data(self._controller.get_nfc())
        if self.nfc_tag_data and self.nfc_state in (NFC_state.POLL, NFC_state.POLL_AGAIN):
            out[8:16] = bytes.fromhex("0000000101020007")
            out[16:19] = self.nfc_tag_data[0:3]
            out[19:23] = self.nfc_tag_data[4:8]
            self.nfc_state = NFC_state.POLL_AGAIN
        out[-1] = MCU_crc(out[0:-1])
        self._queue_response(out)
        self._queue_response(out)
        return out

    # I don't actually know if we are supposed to change the MCU-data based on
    # regular subcommands, but the switch is spamming the status-requests anyway,
    # so sending responses seems to not hurt

    def set_power_state_cmd(self, power_state):
        logger.info(f"MCU: Set power state cmd {power_state}")
        if power_state in SET_POWER_VALUES:
            self.power_state = MCUPowerState(power_state)
        else:
            logger.error(f"not implemented power state {power_state}")
            self.power_state = MCUPowerState.READY
        self._queue_response(self._get_status_data())

    def set_config_cmd(self, config):
        if self.power_state == MCUPowerState.SUSPENDED:
            if config[2] == 0:
                # the switch does this during initial setup, presumably to disable
                # any MCU weirdness
                pass
            else:
                logger.warning("Set MCU Config not in READY mode")
        elif self.power_state == MCUPowerState.READY:
            if config[2] in SET_CONFIG_VALUES:
                self.power_state = MCUPowerState(config[2])
                self.configuration = config
                logger.info(f"MCU Set configuration {self.power_state} {self.configuration}")
            else:
                self.power_state = MCUPowerState.READY
                logger.error(f"Not implemented configuration written {config[2]} {config}")
            if self.power_state == MCUPowerState.CONFIGURED_NFC:
                self.nfc_state = NFC_state.NONE
            self._queue_response(self._get_status_data())

    def handle_nfc_subcommand(self, com, data):
        """
        This generates responses for NFC commands and thus implements the entire
        NFC-behaviour
        @param com: the NFC-command (not the 0x02, the byte after that)
        @param data: the remaining data
        """
        if com == 0x04:  # status / response request
            self._queue_response(self._get_nfc_status_data(data))
        elif com == 0x01:  # start polling, should we queue a nfc_status?
            logger.info("MCU-NFC: start polling")
            self.nfc_state = NFC_state.POLL
        elif com == 0x06:  # read, we probably should not respond to this at all,
            # since each packet is queried individually by the switch, but parsing these
            # 04 packets is just annoying
            logger.info("MCU-NFC: reading...")
            if self.nfc_tag_data:
                self._flush_response_queue()
                # Data is sent in 2 packages plus a trailer
                # the first one contains a lot of fixed header and the UUID
                # the length and packetnumber is in there somewhere, see
                # https://github.com/CTCaer/jc_toolkit/blob/5.2.0/jctool/jctool.cpp line 2523ff
                out = [0] * 313
                out[0:15] = bytes.fromhex("3a0007010001310200000001020007")
                out[15:18] = self.nfc_tag_data[0:3]
                out[18:22] = self.nfc_tag_data[4:8]
                out[22:67] = bytes.fromhex(
                    "000000007DFDF0793651ABD7466E39C191BABEB856CEEDF1CE44CC75EAFB27094D087AE803003B3C7778860000")
                out[67:-1] = self.nfc_tag_data[0:245]
                out[-1] = MCU_crc(out[0:-1])
                self._force_queue_response(out)
                # the second one is mostely data, followed by presumably anything (zeroes work)
                out = [0] * 313
                out[0:7] = bytes.fromhex("3a000702000927")
                out[7:302] = self.nfc_tag_data[245:540]
                out[-1] = MCU_crc(out[0:-1])
                self._force_queue_response(out)
                # the trailer includes the UUID again
                out = [0] * 313
                out[0:16] = bytes.fromhex("2a000500000931040000000101020007")
                out[16:19] = self.nfc_tag_data[0:3]
                out[19:23] = self.nfc_tag_data[4:8]
                out[-1] = MCU_crc(out[0:-1])
                self._force_queue_response(out)
                self.reading = 3
                for msg in self.response_queue:
                    print("MCU-NFC: reading, queued", msg)
                #self.nfc_tag_data = None
                #if self.remove_nfc_after_read:
                #    self._controller.set_nfc(None)
        # elif com == 0x00: # cancel eveyhting -> exit mode?
        elif com == 0x02:  # stop polling, respond?
            logger.info("MCU-NFC: stop polling...")
            self.nfc_state = NFC_state.NONE
        else:
            logger.error("unhandled NFC subcommand", com, data)

    def received_11(self, subcommand, subcommanddata):
        """
        This function handles all 0x11 output-reports.
        @param subcommand: the subcommand as integer
        @param subcommanddata: the remaining data
        @return: None
        """
        if subcommand == 0x01:
            # status request
            self._queue_response(self._get_status_data(subcommanddata))
        elif subcommand == 0x02:
            # NFC command
            if self.power_state != MCUPowerState.CONFIGURED_NFC:
                logger.warning("NFC command outside NFC mode, ignoring", subcommand, subcommanddata)
            else:
                self.handle_nfc_subcommand(subcommanddata[0], subcommanddata[1:])
        else:
            logger.error("unknown 11 subcommand", subcommand, subcommanddata)

    def get_data(self):
        """
        The function returning what is to write into mcu data of tha outgoing 0x31 packet

        usually it is some queued response
        @return: the data
        """
        if self.reading > 0:
            print("sending", self.response_queue[0])
            self.reading -= 1
        if len(self.response_queue) > 0:
            return self.response_queue.pop(0)
        else:
            return self.no_response
