
# MCU
MarvelCinematicUniverse?

This is a chip on the switch's controllers handling all kinds of high data throughput stuff.

There seem to be 5 modes (OFF, starting, ON, NFC, IR, UPDATE) and a 'busy' flag.

Requests are being sent by the switch using 11 output reports, responses are piggibacked to regular input using the MCU-datafield in 31 input reports (and everything is sent as a response to a request). All responses feature a checksum in the last byte that is computed as follows:

checksum: `[crc8(mcu_data[0:-1])]`

Request notation: The values given will always be the byte after `a2` and the one ten bytes after that (maybe followed by subsequent bytes)

All numbers are in continuous hexadecimal

# Generic MCU requests

* If there is no response to be sent, the MCU-datafield is

  `no_request`: `ff00....00[checksum]`

* At first 31 mode is enabled. (`01 0331`)

  `response`: `0100...00[checksum]`

* then the MCU is enabled (`01 2201`)

  the MCU goes through starting -> firmware-update -> on, not sure if we have to respond to this, the next command is always a status request so sending this dosn't hurt.

  The firware-update phase can (and should) be skipped.

  response: `[status | no_request]`

* A status request (`11 01`), response:

  `status`: `0100[busy]0008001b[power_state]`

  where busy is `ff` after initial enable for a while, then goes to `00`
and power_state is `01` for off, `00` for starting, `01` for on, `04` for NFC mode, `06` for firmware-update (this is not sure)

## NFC & Amiibo

Here I describe what I found the nfc-reading process of amiibos looks like:

### generic stuff:

* the Tag data `nfc_data` is 540 bytes in length

* the UID is 7 of those bytes a follows:

  `tag_uid`: `[nfc_data(0;3(][nfc_data(4;8(]`

### NFC Requests

* command: configure NFC (`01 2121`)

  response: nothing (but the command-ack is weird)

* get status / start discovery: `11 0204`

  This is spammed like hell and seems to be some other kind of nfc-status-request

  `nfc_status`: `2a000500000931[nfc_state]`

  where nfc_state is
  - `00` for nothing/polling startup or something like this
  - `01` for polling without success
  - `01` for polling with success, followed by `poll_success`: `0000000101020007[tag_uid]`
  - `02` for pending read, followed by `[poll_success]`
  - `09` for polling with success, same tag as last time, followed by `[poll_success]`

  Note: the joycon thrice reported 09 followed by just 00. in response to 0204 commands after stop-polling

* poll (`11 0201`)

  look for a new nfc tag now

  response: noting, maybe `[nfc_status]`

* read (`11 0206`)

  respond with the 3 read packets read1 read2 read3 followed by no_request

  Note: it seems every packet is requested individually using a 0204, as on of the bytes in the request increments from 0 to 3 shortly before/after the data is sent.

  the Packets:

  read1: `3a0007010001310200000001020007[TAG_UID]000000007DFDF0793651ABD7466E39C191BABEB856CEEDF1CE44CC75EAFB27094D087AE803003B3C7778860000[nfc_data(0;245(][checksum]`

  read2: `3a000702000927[nfc data (245;540(][checksum]`

  read3: `2a000500000931040000000101020007[TAG_UID]00...00[checksum]`

* stop polling (`11 0202`)

  after a poll, presumably stop looking for a tag discovered during poll command

  no response

* cancel (`11 0200`)

  No idea
