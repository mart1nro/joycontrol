import enum
import logging
import crc8
import traceback
import asyncio

from joycontrol.controller_state import ControllerState
from joycontrol.nfc_tag import NFCTag

logger = logging.getLogger(__name__)


###############################################################
## This simulates the MCU in the right joycon/Pro-Controller ##
###############################################################
# WARNING: THIS IS ONE GIANT RACE CONDITION, DON'T DO THINGS FAST
# No I won't fix this, I have had enough of this asyncio b***s***
# DIY or STFU
# This is sufficient to read or write one amiibo when simulating
# a Pro-Controller
# multiple can mess up the internal state
# anything but amiboo is not supported
# TODO:
#     - figure out the NFC-content transfer, currently everything is hardcoded to work wich amiibo
#       see https://github.com/CTCaer/jc_toolkit/blob/5.2.0/jctool/jctool.cpp l2456ff for sugesstions
#     - IR-camera
#     - writing to Amiibo the proper way
#     - verify right joycon
#     - Figure out the UID index in write commands, currently the check is just uncommented...

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
    PROCESSING_WRITE = 0x05
    POLL_AGAIN = 0x09


def pack_message(*args, background=0, checksum=MCU_crc, length=313):
    """
    convinience function that packes
    * hex strings
    * byte lists
    * integer lists
    * Enums
    * integers
    into a 313 bytes long MCU response
    """
    data = bytearray([background] * length)
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
        if arg_len + cur > length:
            logger.warning("MCU: too long message packed")
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

        self.nfc_state = NFC_state.NONE
        # Counter for testing state transitions
        self.nfc_counter = 0

        self._last_poll_uid = None

        # after writing we need to "remove" the amiibo
        # sending the detection of a bunch of zeros works
        # (pretty sure it just panics the switch)
        self.remove_amiibo = NFCTag(data=bytes(540))
        # weather or not the next n POLLs without a tag should assume the remove_amiibo
        self._pending_active_remove = 0

        # remove the tag from the controller after a successful read
        # NOT IMPLEMENTED self.remove_nfc_after_read = False
        # remove the tag from the controller after a successful write, the switch demands this
        self.remove_nfc_after_write = True

        # controllerstate to look for nfc-data
        self._controller = controller

        # long messages are split, this keeps track of in and outgoing transfers
        self.seq_no = 0
        self.ack_seq_no = 0
        # self.expect_data = False
        self.received_data = []

        # We are getting 0x11 commands to do something, but cannot answer directly
        # responses have to be passed in regular input reports
        # If there was no command, this is the default report
        self.no_response = pack_message(0xff)
        self.response_queue = []
        # to prevent the queue from becoming too laggy, limit it's size
        # the length after which we start dropping packets
        self.max_response_queue_len = 4

    def _flush_response_queue(self):
        self.response_queue = []

    def _queue_response(self, resp):
        if len(self.response_queue) < self.max_response_queue_len:
            self.response_queue.append(resp)
        else:
            logger.warning("Full queue, dropped outgoing MCU packet")

    # used to queue messages that cannot be dropped, as we don't have any kind of resend-mechanism
    def _force_queue_response(self, resp):
        self.response_queue.append(resp)
        if len(self.response_queue) > self.max_response_queue_len:
            logger.warning("Forced response queue")

    def set_remove_nfc_after_read(self, value):
        pass
        # self.remove_nfc_after_read = value

    def _get_status_data(self, args=None):
        """
        create a status packet to be used when responding to 1101 commands (outside NFC-mode)
        """
        if self.power_state == MCUPowerState.SUSPENDED:
            logger.warning("MCU: status request when disabled")
            return self.no_response
        elif self.power_state.value in GET_STATUS_VALUES:
            return pack_message("0100000008001b", self.power_state)

    def _get_nfc_status_data(self, args):
        """
        Generate a NFC-Status report to be sent back to switch
        This is 40% of all logic in this file, as all we do in NFC-mode is send these responses
        but some (the read/write-tag ones) are hardcoded somewhere else
        @param args: not used
        @return: the status-message
        """
        self.nfc_counter -= 1
        nfc_tag = self._controller.get_nfc()

        # after a write to get out of the screen report the empty amiibo
        if self.nfc_state in (NFC_state.POLL, NFC_state.POLL_AGAIN) and (self.remove_nfc_after_write or not nfc_tag) and self._pending_active_remove > 0:
            nfc_tag = self.remove_amiibo
            self._pending_active_remove -= 1

        if self.nfc_state == NFC_state.PROCESSING_WRITE and self.nfc_counter <= 0:
            self.nfc_state = NFC_state.NONE
        elif self.nfc_state == NFC_state.POLL:
            if nfc_tag and nfc_tag.getUID() == self._last_poll_uid:
                self.nfc_state = NFC_state.POLL_AGAIN
            else:
                self._last_poll_uid = nfc_tag.getUID() if nfc_tag else None
        elif self.nfc_state == NFC_state.POLL_AGAIN:
            if not nfc_tag or nfc_tag.getUID() != self._last_poll_uid:
                self.nfc_state = NFC_state.POLL
                self._last_poll_uid = nfc_tag.getUID() if nfc_tag else None

        if nfc_tag and self.nfc_state != NFC_state.NONE:
            # states POLL, POLL_AGAIN, AWAITING_WRITE, WRITING, PROCESSING_WRITE can include the UID
            out = pack_message("2a0005", self.seq_no, self.ack_seq_no, "0931", self.nfc_state,
                               "0000000101020007", nfc_tag.getUID())
        else:  # seqno and ackseqno should be 0 if we're not doing anything fancy
            out = pack_message("2a000500000931", self.nfc_state)

        return out

    async def process_nfc_write(self, command):
        """
        After all data regarding the write to the tag has been received, this function actually applies the changed
        @param command: the entire write request
        @return: None
        """
        logger.info("MCU: processing nfc write")
        nfc_tag: NFCTag = self._controller.get_nfc()
        if not nfc_tag:
            logger.error("nfc_tag is none, couldn't write")
            return
        if command[1] != 0x07:  # panic wrong UUID length
            logger.error(f"UID length is {command[1]} (not 7), aborting")
            return
        if bytes(command[2:9]) != nfc_tag.getUID():
            logger.error(f"self.nfc_tag.uid and target uid aren't equal, are {bytes(nfc_tag.getUID()).hex()} and {bytes(command[2:9]).hex()}")
            # return # wrong UUID, won't write to wrong UUID
        if nfc_tag.is_mutable():
            nfc_tag.create_backup()
        else:
            nfc_tag.set_mutable(True)

        # write write-lock
        nfc_tag.data[16:20] = command[13:17]

        i = 22
        while i + 1 < len(command):
            addr = command[i] * 4
            leng = command[i + 1]
            data = command[i + 2:i + 2 + leng]
            if addr == 0 or leng == 0:
                break
            nfc_tag.write(addr, data)
            i += 2 + leng

        # remove write lock
        nfc_tag.data[16:20] = command[17:21]
        nfc_tag.save()
        return

    def handle_nfc_subcommand(self, com, data):
        """
        This generates responses for NFC commands and thus implements the entire
        NFC-behaviour
        @param com: the NFC-command (not the 0x02, the byte after that)
        @param data: the remaining data
        """
        if com == 0x04:  # status / response request
            # the switch spams this up to 8 times a frame, there is no way to respond to all
            self._queue_response(self._get_nfc_status_data(data))
        elif com == 0x01:  # start polling, should we queue a nfc_status?
            logger.debug("MCU-NFC: start polling")
            self.nfc_state = NFC_state.POLL
        elif com == 0x06:  # read/write
            logger.debug(f"MCU-NFC Read/write {data[6:13]}")
            nfc_tag = self._controller.get_nfc()
            if nfc_tag:
                # python usually doesn't care about data-types but a list is not an array.... how I hate this crap
                if bytes(data[6:13]) == bytes(7):  # This is the UID, 0 means read anything
                    logger.info("MCU-NFC: reading Tag...")
                    self._flush_response_queue()
                    # Data is sent in 2 packages plus a trailer
                    # the first one contains a lot of fixed header and the UUID
                    # the length and packetnumber is in there somewhere, see
                    # https://github.com/CTCaer/jc_toolkit/blob/5.2.0/jctool/jctool.cpp line 2523ff
                    self._force_queue_response(pack_message(
                        "3a0007010001310200000001020007",
                        nfc_tag.getUID(),
                        "000000007DFDF0793651ABD7466E39C191BABEB856CEEDF1CE44CC75EAFB27094D087AE803003B3C7778860000",
                        nfc_tag.data[0:245]
                    ))
                    # the second one is mostely data, followed by presumably anything (zeroes work)
                    self._force_queue_response(pack_message(
                        "3a000702000927",
                        nfc_tag.data[245:540]
                    ))
                    # the trailer includes the UUID again
                    # this is not actually the trailer, joycons send both packets again but with the first bytes in the
                    # first one 0x2a then this again. But it seems to work without?
                    self._force_queue_response(pack_message(
                        "2a000500000931040000000101020007",
                        nfc_tag.getUID()
                    ))
                # elif bytes(data[6:13]) == nfc_tag.getUID():  # we should check the UID
                else:  # the UID is nonzero, so I a write to that tag follows
                    logger.info(f"MCU-NFC: setup writing tag {data[6:13]}")
                    self._force_queue_response(pack_message(
                        "3a0007010008400200000001020007", nfc_tag.getUID(),  # standard header for write, some bytes differ from read
                        "00000000fdb0c0a434c9bf31690030aaef56444b0f602627366d5a281adc697fde0d6cbc010303000000000000f110ffee"
                        # any guesses are welcome. The end seems like something generic, a magic number?
                    ))
                    self.received_data = []
                    self.nfc_state = NFC_state.AWAITING_WRITE
            else:
                logger.error("had no NFC tag when read/write was initiated")
        # elif com == 0x00: # cancel eveyhting -> exit mode?
        elif com == 0x02:  # stop polling, respond?
            logger.debug("MCU-NFC: stop polling...")
            self.nfc_state = NFC_state.NONE
            self._last_poll_uid = None
        elif com == 0x08:  # write NTAG
            if data[0] == 0 and data[2] == 0x08:  # never seen, single packet as entire payload
                asyncio.ensure_future(self.process_nfc_write(data[4: 4 + data[3]]))
                logger.warning("MCU-NFC write valid but WTF")
                return
            if data[0] <= self.ack_seq_no:  # we already saw this one
                logger.info(f"MCU-NFC write packet repeat {data[0]}")
                pass
            elif data[0] == 1 + self.ack_seq_no:  # next packet in sequence
                self.received_data += data[4: 4 + data[3]]
                self.ack_seq_no += 1
                logger.debug(f"MCU-NFC write packet {self.ack_seq_no}")
            else:  # panic we missed/skipped something
                logger.warning(f"MCU-NFC write unexpected packet, expected {self.ack_seq_no} got {data[0]}, aborting.")
                self.ack_seq_no = 0
            self.nfc_state = NFC_state.WRITING
            self._force_queue_response(self._get_nfc_status_data(data))
            if data[2] == 0x08:  # end of sequence
                self.ack_seq_no = 0
                self.nfc_state = NFC_state.PROCESSING_WRITE
                self.nfc_counter = 4
                self._pending_active_remove = 4 # Dunno, anything > 2 works most likely
                asyncio.ensure_future(self.process_nfc_write(self.received_data))
        else:
            logger.error("unhandled NFC subcommand", com, data)

    # I don't actually know if we are supposed to change the MCU-data based on
    # regular subcommands, but the switch is spamming the status-requests anyway,
    # so sending responses seems to not hurt

    # protocoll-callback
    def entered_31_input_mode(self):
        self._flush_response_queue()
        self.power_state = MCUPowerState.READY
        self._queue_response(self._get_status_data())

    # protocoll-callback
    def set_power_state_cmd(self, power_state):
        logger.debug(f"MCU: Set power state cmd {power_state}")
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
                logger.debug(f"MCU Set configuration {self.power_state} {self.configuration}")
            else:
                self.power_state = MCUPowerState.READY
                logger.error(f"Not implemented configuration written {config[2]} {config}")
            if self.power_state == MCUPowerState.CONFIGURED_NFC:
                # reset all nfc-related parts
                self.nfc_state = NFC_state.NONE
                self.nfc_counter = 0
                self.seq_no = 0
                self.ack_seq_no = 0
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
                logger.warning(f"NFC command ({subcommand} {subcommanddata}) outside NFC mode, ignoring")
            else:
                self.handle_nfc_subcommand(subcommanddata[0], subcommanddata[1:])
        else:
            logger.error(f"unknown 0x11 subcommand {subcommand} {subcommanddata}")

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
