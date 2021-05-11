import socket
from struct import pack

hci = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_RAW, socket.BTPROTO_HCI)
hci.bind((0,))
# 0x10 = 1 << 4 = HCI_EVT

# first arg (0x10): 1 << MESSAGE_TYPE  For multiple "or" them together
# 2nd and 3rd arg: subtypes you want. same format as first arg. For event called "EVENT CODE"
# 2nd arg for the first 32 Codes, 3rd arg for 33-64.
# 4th arg: dunno, 0 works
hci.setsockopt(socket.SOL_HCI, socket.HCI_FILTER, pack("IIIh2x", 0x10, 1 << 0x1b, 0, 0))
#hci.setsockopt(socket.SOL_HCI, socket.HCI_FILTER, pack("IIIh2x", 0xFFFFFFFF, 0xFFFFFFFF, 0xFFFFFFFF, 0))

while True:
    print(hci.recv(300).hex())
