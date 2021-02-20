import enum
import logging
import crc8
import traceback
import asyncio

from joycontrol.controller_state import ControllerState
from joycontrol.nfc_tag import NFCTag

logger = logging.getLogger(__name__)


def debug(args):
    print(args)
    return args


###############################################################
## This simulates the MCU in the right joycon/Pro-Controller ##
###############################################################
# This is sufficient to read one amiibo when simulation Pro-Controller
# multiple can mess up the internal state
# anything but amiboo is not supported
# TODO:
#     - figure out the NFC-content transfer, currently everything is hardcoded to work wich amiibo
#       see https://github.com/CTCaer/jc_toolkit/blob/5.2.0/jctool/jctool.cpp l2456ff for sugesstions
#     - IR-camera
#     - writing to Amiibo
#     - verify right joycon

# These Values are used in set_power, set_config and get_status packets
# But not all of them can appear in every one
# see https://github.com/CTCaer/jc_toolkit/blob/5.2.0/jctool/jctool.cpp l 2359 for set_config
class MCUPowerState(enum.Enum):
    SUSPENDED = 0x00  # set_power
    READY = 0x01  # set_power, set_config, get_status
    READY_UPDATE = 0x02
    CONFIGURED_NFC = 0x04  # set_config, get_status
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
    WRITING = 0x03
    AWAITING_WRITE = 0x04
    POLL_AGAIN = 0x09


def pack_message(*args, background=0, checksum=MCU_crc):
    """
    convinience function that packes
    * hex strings
    * byte lists
    * integer lists
    * Enums
    * integers
    into a 313 bytes long MCU response
    """
    data = bytearray([background] * 313)
    cur = 0
    for arg in args:
        if isinstance(arg, str):
            arg = bytes.fromhex(arg)
        elif isinstance(arg, int):
            arg = bytes([arg])
        elif isinstance(arg, enum.Enum):
            arg = bytes([arg.value])
        else:
            arg = bytes(arg)
        arg_len = len(arg)
        if arg_len + cur > 313:
            logger.warn("MCU: too long message packed")
        data[cur:cur + arg_len] = arg
        cur += arg_len
    if checksum:
        data[-1] = checksum(data[0:-1])
    return data


class MicroControllerUnit:
    def __init__(self, controller: ControllerState):

        self.power_state = MCUPowerState.SUSPENDED

        # NOT USED
        # Just a store for the remaining configuration data
        self.configuration = None

        # a cache to store the tag's data between Poll and Read
        self.nfc_tag: NFCTag = None
        self.nfc_state = NFC_state.NONE

        # NOT IMPLEMENTED
        # remove the tag from the controller after a successfull read
        self.remove_nfc_after_read = False

        # controllerstate to look for nfc-data
        self._controller = controller

        self.seq_no = 0
        self.ack_seq_no = 0
        # self.expect_data = False
        self.received_data = []

        # We are getting 0x11 commands to do something, but cannot answer directly
        # responses have to be passed in regular input reports
        # If there was no command, this is the default report
        self.no_response = pack_message(0xff)
        self.response_queue = []
        # to prevent overfill of the queue drops packets, but some are integral.
        self.response_queue_importance = []
        # the length after which we start dropping packets
        self.max_response_queue_len = 4

    def _flush_response_queue(self):
        self.response_queue = []

    def _queue_response(self, resp):
        if resp == None:  # the if "missing return statement" because python
            traceback.print_stack()
            exit(1)
        if len(self.response_queue) < self.max_response_queue_len:
            self.response_queue.append(resp)
        else:
            logger.warning("Full queue, dropped packet")

    def _force_queue_response(self, resp):
        self.response_queue.append(resp)
        if len(self.response_queue) > self.max_response_queue_len:
            logger.warning("Forced response queue")

    def set_remove_nfc_after_read(self, value):
        self.remove_nfc_after_read = value

    # called somwhere in get_nfc_status with _controller.get_nfc()
    def set_nfc_tag(self, tag: NFCTag):
        logger.info("MCU-NFC: set NFC tag data")
        if not isinstance(tag, NFCTag):
            # I hope someone burns in hell for this bullshit...
            print("NOT A NFC TAG DUMBO")
            exit(-1)
        if not tag:
            self.nfc_tag = None
        self.nfc_tag = tag

    def _get_status_data(self, args=None):
        """
        create a status packet to be used when responding to 1101 commands
        """
        if self.power_state == MCUPowerState.SUSPENDED:
            logger.warning("MCU: status request when disabled")
            return self.no_response
        elif self.power_state.value in GET_STATUS_VALUES:
            return pack_message("0100000008001b", self.power_state)

    def _get_nfc_status_data(self, args):
        next_state = self.nfc_state
        if self.nfc_state == NFC_state.POLL and self._controller.get_nfc():
            self.set_nfc_tag(self._controller.get_nfc())
            next_state = NFC_state.POLL_AGAIN
            logger.info("polled and found tag")
        if self.nfc_tag and self.nfc_state in (NFC_state.POLL, NFC_state.POLL_AGAIN, NFC_state.AWAITING_WRITE, NFC_state.WRITING):
            out = pack_message("2a0005", self.seq_no, self.ack_seq_no, "0931", self.nfc_state, "0000000101020007",
                               self.nfc_tag.getUID())
        else:
            out = pack_message("2a000500000931", self.nfc_state)
        self.nfc_state = next_state
        return out

    async def process_nfc_write(self, command):
        if not self.nfc_tag:
            return
        if command[1] != 0x07:  # panic wrong UUID length
            return
        if command[2:9] != self.nfc_tag.getUID():
            return # wrong UUID, won't write to wrong UUID
        self.nfc_tag = self.nfc_tag.get_mutable()
        self.nfc_tag.write(command[12] * 4, command[13:13 + 4])
        i = 22
        while i + 1 < len(command):
            addr = command[i] * 4
            len = command[i + 1]
            data = command[i + 2:i + 2 + len]
            self.nfc_tag.write(addr, len, data)
            i += 2 + len
        return

    def handle_nfc_subcommand(self, com, data):
        """
        This generates responses for NFC commands and thus implements the entire
        NFC-behaviour
        @param com: the NFC-command (not the 0x02, the byte after that)
        @param data: the remaining data
        """
        if com == 0x04:  # status / response request
            self._force_queue_response(self._get_nfc_status_data(data))
        elif com == 0x01:  # start polling, should we queue a nfc_status?
            logger.info("MCU-NFC: start polling")
            self.nfc_state = NFC_state.POLL
        elif com == 0x06:  # read
            # IT FUCKING KNOWS THIS IS A ARGUMENT, JUST CRASHES FOR GOOD MEASURE
            logger.info("MCU-NFCRead %s", data[6:13])
            # this language gives no f*** about types, but a byte is no integer....
            if all(map(lambda x, y: x == y, data[6:13], bytearray(7))):  # This is the UID, 0 seems to mean read anything
                logger.info("MCU-NFC: reading Tag...")
                if self.nfc_tag:
                    self._flush_response_queue()
                    # Data is sent in 2 packages plus a trailer
                    # the first one contains a lot of fixed header and the UUID
                    # the length and packetnumber is in there somewhere, see
                    # https://github.com/CTCaer/jc_toolkit/blob/5.2.0/jctool/jctool.cpp line 2523ff
                    self._force_queue_response(pack_message(
                        "3a0007010001310200000001020007",
                        self.nfc_tag.getUID(),
                        "000000007DFDF0793651ABD7466E39C191BABEB856CEEDF1CE44CC75EAFB27094D087AE803003B3C7778860000",
                        self.nfc_tag.data[0:245]
                    ))
                    # the second one is mostely data, followed by presumably anything (zeroes work)
                    self._force_queue_response(pack_message(
                        "3a000702000927",
                        self.nfc_tag.data[245:540]
                    ))
                    # the trailer includes the UUID again
                    # this is not actually the trailer, joycons send both packets again but with the first bytes in the
                    # first one 0x2a then this again. But it seems to work without?
                    self._force_queue_response(pack_message(
                        "2a000500000931040000000101020007",
                        self.nfc_tag.getUID()
                    ))
            else:  # the UID is nonzero, so I assume a read follows
                print("writing", data[6:13])
                self._force_queue_response(pack_message(
                    "3a0007010008400200000001020007", self.nfc_tag.getUID(),  # standard header for write, some bytes differ
                    "00000000fdb0c0a434c9bf31690030aaef56444b0f602627366d5a281adc697fde0d6cbc010303000000000000f110ffee"
                    # any guesses are welcome. The end seems like something generic, a magic number?
                ))
                self.nfc_state = NFC_state.AWAITING_WRITE
        # elif com == 0x00: # cancel eveyhting -> exit mode?
        elif com == 0x02:  # stop polling, respond?
            logger.info("MCU-NFC: stop polling...")
            self.nfc_state = NFC_state.NONE
        elif com == 0x08:  # write NTAG
            if data[0] == 0 and data[2] == 0x08:  # never seen, single packet as entire payload
                asyncio.ensure_future(self.process_nfc_write(data[4: 4 + data[3]]))
                return
            if data[0] == self.ack_seq_no:  # we already saw this one
                pass
            elif data[0] == 1 + self.ack_seq_no:  # next packet in sequence
                self.received_data += data[4: 4 + data[3]]
                self.ack_seq_no += 1
            else:  # panic we missed/skipped something
                self.ack_seq_no = 0
            self.nfc_state = NFC_state.WRITING
            self._force_queue_response(self._get_nfc_status_data(data))
            if data[2] == 0x08:  # end of sequence
                self.ack_seq_no = 0
                asyncio.ensure_future(self.process_nfc_write(self.received_data))
        else:
            logger.error("unhandled NFC subcommand", com, data)

    # I don't actually know if we are supposed to change the MCU-data based on
    # regular subcommands, but the switch is spamming the status-requests anyway,
    # so sending responses seems to not hurt

    # protocoll-callback
    def entered_31_input_mode(self):
        self._flush_response_queue()
        self._queue_response(pack_message("0100000008001b01"))

    # protocoll-callback
    def set_power_state_cmd(self, power_state):
        logger.info(f"MCU: Set power state cmd {power_state}")
        self._flush_response_queue()
        if power_state in SET_POWER_VALUES:
            self.power_state = MCUPowerState(power_state)
        else:
            logger.error(f"not implemented power state {power_state}")
            self.power_state = MCUPowerState.READY
        self._queue_response(self._get_status_data())

    # protocoll-callback
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

    # protocoll-callback
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

    # protocoll hook
    def get_data(self):
        """
        The function returning what is to write into mcu data of tha outgoing 0x31 packet

        usually it is some queued response
        @return: the data
        """
        if len(self.response_queue) > 0:
            return self.response_queue.pop(0)
        else:
            return self.no_response
