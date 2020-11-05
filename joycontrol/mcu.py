import enum
import logging
import crc8

from joycontrol.controller_state import ControllerState

logger = logging.getLogger(__name__)

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

class MCUPowerState(enum.Enum):
    SUSPENDED = 0x00
    READY = 0x01
    READY_UPDATE = 0x02
    CONFIGURED_NFC = 0x10
    CONFIGURED_IR = 0x11  # TODO: support this

def MCU_crc(data):
    if not isinstance(data, bytes):
        data = bytes(data)
    my_hash = crc8.crc8()
    my_hash.update(data)
    # At this point I'm not even mad this works...
    return my_hash.digest()[0]


class MarvelCinematicUniverse:
    def __init__(self, controller: ControllerState):

        self.power_state = MCUPowerState.SUSPENDED

        # NOT USED
        # Just a store for the remaining configuration data
        self.configuration = None

        # a cache to store the tag's data during reading
        self.nfc_tag_data = None
        # reading is done in multiple packets
        # https://github.com/CTCaer/jc_toolkit/blob/5.2.0/jctool/jctool.cpp line 2537
        # there seem to be some flow-controls and order-controls in this process
        # which is all hardcoded here
        self.reading_cursor = None

        # NOT IMPLEMENTED
        # remove the tag from the controller after a successfull read
        self.remove_nfc_after_read = False

        # controllerstate to look for nfc-data
        self._controller = controller

        # We are getting 0x11 commands to do something, but cannot answer directly
        # answers are passed inside the input-reports that are sent regularly
        # they also seem to just be repeated until a new request comes in
        self.response = [0] * 313

    def set_remove_nfc_after_read(self, value):
        self.remove_nfc_after_read = value

    def set_nfc_tag_data(self, data):
        if not data:
            self.nfc_tag_data = None
        if not data is bytes:
            data = bytes(data)
        if len(data) != 540:
            logger.warning("not implemented length")
            return
        self.nfc_tag_data = data

    def _get_status_data(self):
        """
        create a status packet to be used when responding to 1101 commands
        """
        out = [0] * 313
        if self.power_state == MCUPowerState.SUSPENDED:
            return out
        else:
            out[0:7] = bytes.fromhex("01000000030005")
            if self.power_state == MCUPowerState.CONFIGURED_NFC:
                out[7] = 0x04
            else:
                out[7] = 0x01
        out[-1] = MCU_crc(out[0:-1])
        return out

    # I don't actually know if we are supposed to change the MCU-data based on
    # regular subcommands, but the switch is spamming the status-requests anyway,
    # so sending responses seems to not hurt

    def set_power_state_cmd(self, power_state):
        # 1 == (READY = 1) evaluates to false. WHY?
        if power_state in (MCUPowerState.SUSPENDED.value, MCUPowerState.READY.value):
            self.power_state = MCUPowerState(power_state)
            self.response = [0] * 313
        if power_state == MCUPowerState.READY_UPDATE:
            logger.error("NFC Update not implemented")
        print(f"MCU: went into power_state {power_state}")
        if self.power_state == MCUPowerState.SUSPENDED:
            # the response probably doesnt matter.
            self.response[0] = 0xFF
            self.response[-1] = 0x6F
        elif self.power_state == MCUPowerState.READY:
            # this one does however
            self.response[1] = 1
            self.response[-1] = 0xc1

    def set_config_cmd(self, config):
        if self.power_state == MCUPowerState.SUSPENDED:
            if config[3] == 0:
                # the switch does this during initial setup, presumably to disable
                # any MCU weirdness
                pass
            else:
                logger.warning("Set MCU Config not in READY mode")
        elif self.power_state == MCUPowerState.READY:
            self.configuration = config
            logger.info(f"MCU Set configuration{self.configuration}")
            self.response[0:7] = bytes.fromhex("01000000030005")
            # see https://github.com/CTCaer/jc_toolkit/blob/5.2.0/jctool/jctool.cpp l 2359 for values
            if config[2] == 4:
                # configure into NFC
                self.response[7] = 0x04
                self.power_state = MCUPowerState.CONFIGURED_NFC
            elif config[2] == 1:
                # deconfigure / disable
                self.response[7] = 0x01
                self.power_state = MCUPowerState.READY
            #elif config[2] == 5: IR-Camera
            #elif config[2] == 6: FW-Update Maybe
            else:
                logger.error("Not implemented configuration written")
                self.response[7] = 0x01
        self.response[-1] = MCU_crc(self.response[0:-1])

    def received_11(self, subcommand, subcommanddata):
        if self.reading_cursor is not None:
            return
        self.response = [0] * 313
        if subcommand == 0x01:
            # status request, respond with string and Powerstate
            self.response[0:7] = bytes.fromhex("01000000030005")
            self.response[7] = 0x04 if self.power_state == MCUPowerState.CONFIGURED_NFC else 0x01
        elif subcommand == 0x02:
            # NFC command
            if self.power_state != MCUPowerState.CONFIGURED_NFC:
                logger.warning("NFC command outside NFC mode, ignoring")
            elif subcommanddata[0] == 0x04:
                # Start discovery
                self.response[0:7] = bytes.fromhex("2a000500000931")
            elif subcommanddata[0] == 0x01:
                # Start polling
                self.set_nfc_tag_data(self._controller.get_nfc())
                if self.nfc_tag_data:
                    # send the tag we found
                    self.response[0:16] = bytes.fromhex("2a000500000931090000000101020007")
                    self.response[16:19] = self.nfc_tag_data[0:3]
                    self.response[19:23] = self.nfc_tag_data[4:8]
                else:
                    # send found nothing
                    self.response[0:8] = bytes.fromhex("2a00050000093101")
                    # we could report the tag immediately, but the switch doesn't like too much success
                    # TODO: better way to delay tag detection
                    logger.info("MCU: Looking for tag")
            elif subcommanddata[0] == 0x06:
                # start reading
                if not self.reading_cursor:
                    self.reading_cursor = 0
            #elif subcommanddata[0] == 0x00: # cancel eveyhting -> exit mode?
            elif subcommanddata[0] == 0x02:
                # stop Polling
                # AKA discovery again
                self.response[0:7] = bytes.fromhex("2a000500000931")
        self.response[-1] = MCU_crc(self.response[0:-1])

    def get_data(self):
        if self.reading_cursor is not None:
            # reading seems to be just packets back to back, so we have to rewrite
            # each when sending them
            # TODO: Use a packet queue for this
            self.response = [0] * 313
            if self.reading_cursor == 0:
                # Data is sent in 2 packages plus a trailer
                # the first one contains a lot of fixed header and the UUID
                # the length and packetnumber is in there somewhere, see
                # https://github.com/CTCaer/jc_toolkit/blob/5.2.0/jctool/jctool.cpp line 2523ff
                self.response[0:15] = bytes.fromhex("3a0007010001310200000001020007")
                self.response[15:18] = self.nfc_tag_data[0:3]
                self.response[18:22] = self.nfc_tag_data[4:8]
                self.response[22:67] = bytes.fromhex(
                    "000000007DFDF0793651ABD7466E39C191BABEB856CEEDF1CE44CC75EAFB27094D087AE803003B3C7778860000")
                self.response[67:-1] = self.nfc_tag_data[0:245]
            elif self.reading_cursor == 1:
                # the second one is mostely data, followed by presumably zeroes (zeroes work)
                self.response[0:7] = bytes.fromhex("3a000702000927")
                self.response[7:302] = self.nfc_tag_data[245:540]
            elif self.reading_cursor == 2:
                # the trailer includes the UUID again
                self.response[0:16] = bytes.fromhex("2a000500000931040000000101020007")
                self.response[16:19] = self.nfc_tag_data[0:3]
                self.response[19:23] = self.nfc_tag_data[4:8]
                self.nfc_tag_data = None
                if self.remove_nfc_after_read:
                    self._controller.set_nfc(None)
            elif self.reading_cursor == 3:
                # we are done but still need a graceful shutdown
                # HACK: sending the SUSPENDED response seems to not crash it
                # The next thing the switch requests sometimes is start discovery
                self.reading_cursor = None
                # self.nfc_tag_data = None
                self.response[0] = 0xff
                # if self.remove_nfc_after_read:
                #    self._controller.set_nfc(None)
            if self.reading_cursor is not None:
                self.reading_cursor += 1
            self.response[-1] = MCU_crc(self.response[0:-1])
        return self.response

