import asyncio
import logging
import pickle
import os
import array
import struct
import socket

from joycontrol.protocol import controller_protocol_factory
from joycontrol.transport import L2CAP_Transport


logger = logging.getLogger(__name__)


async def start_share_controller_server(protocol, server_address):
    """Set up and start a sharing controller server.

    Args:
        - protocal: a running protocal instance. 
        - server_address: a Unix socket path.
    """
    loop = asyncio.get_event_loop()

    is_sharing_controller = False

    async def handle_shared_controller_client_connected(conn):
        logger.info("Handling incoming share request...")

        nonlocal is_sharing_controller

        async def return_error(error_msg):
            logger.info("{}; cannot share controller".format(error_msg))
            data = pickle.dumps({"status": "error", "msg": error_msg})
            conn.sendall(array.pack('i', len(data)))
            conn.sendall(data)
            conn.close()

        if is_sharing_controller:
            return await return_error("Controller already shared to other process")

        if not protocol.is_in_0x30_input_report_mode():
            return await return_error("Protocol not in input report 0x30 mode")

        try:
            is_sharing_controller = True
            protocol.pause_input_report_mode_0x30()

            # Transfer the controller owner ship by sending over the bluetooth socket fd
            transport = protocol.transport
            client_itr_fd = transport.get_extra_info("socket").fileno()
            data = pickle.dumps({
                "status": "ok",
                "controller": protocol.controller,
                "spi_flash": protocol.spi_flash
            })
            conn.sendall(struct.pack('i', len(data)))
            conn.sendmsg(
                [b"fd"], 
                [(socket.SOL_SOCKET, socket.SCM_RIGHTS, array.array("i", [client_itr_fd]))])
            await loop.sock_sendall(conn, data)
            await loop.sock_recv(conn, 1) # if we get back anything then we close the connection

        except Exception as ex:
            logger.debug(ex)

        finally:
            conn.close()
            is_sharing_controller = False
            protocol.start_input_report_mode_0x30()
            logger.info("Re-gained Controller")
            return True

    logger.info(
        "Starting unix server at {}; connect to this address to share the controller".format(server_address))
    unix_server_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    os.unlink(server_address)
    unix_server_sock.bind(server_address)
    unix_server_sock.setblocking(False)
    unix_server_sock.listen()
    while True:
        conn, addr = await loop.sock_accept(unix_server_sock)
        await handle_shared_controller_client_connected(conn)


def recv_fds(sock, msglen, maxfds):
    """Function from https://docs.python.org/3/library/socket.html#socket.socket.recvmsg"""
    fds = array.array("i")   # Array of ints
    msg, ancdata, flags, addr = sock.recvmsg(msglen, socket.CMSG_LEN(maxfds * fds.itemsize))
    for cmsg_level, cmsg_type, cmsg_data in ancdata:
        if (cmsg_level == socket.SOL_SOCKET and cmsg_type == socket.SCM_RIGHTS):
            # Append data, ignoring any truncated integers at the end.
            fds.fromstring(cmsg_data[:len(cmsg_data) - (len(cmsg_data) % fds.itemsize)])
    return msg, list(fds)


async def get_shared_controller(server_address, capture_file=None):
    """Communicates with sharing server to setup a shared controller session.
    
    Given a sharing server address, returns a connected protocol object and a server socket.
    The protocol object is a connected session that contains 
    a ready-to-use controller state (running under 0x30 input mode).
    The server_conn is a socket object, which if written or make closed, 
    will close the connection to sharing server immediately. 
    Note that this function do only minimal error handling. 
    The caller is responsible for catching any exception and closing the server connection.

    Args:
        - server_address: a Unix socket path.
        - capture_file: opened file for capturing transport output (for this shared session).

    Returns:
        A pair of (protocol, server_conn).
    """

    loop = asyncio.get_event_loop()

    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    await loop.sock_connect(sock, server_address)

    data_len, = struct.unpack('i', await loop.sock_recv(sock, 4))

    msg, fds = recv_fds(sock, 2, 1)
    assert msg == b"fd"

    msg = b''
    while len(msg) < data_len:
        msg += await loop.sock_recv(sock, data_len - len(msg))

    msg = pickle.loads(msg)
    if msg.get("status") != "ok":
        raise ValueError("Failed to connect to controller server: {}".format(msg.get("msg", "unknown error")))
    
    client_itr = socket.fromfd(fds[0], socket.AF_BLUETOOTH, socket.SOCK_SEQPACKET, socket.BTPROTO_L2CAP)
    controller, spi_flash = msg['controller'], msg['spi_flash']
    protocol = controller_protocol_factory(controller, spi_flash=spi_flash)()
    transport = L2CAP_Transport(asyncio.get_event_loop(), protocol, client_itr, 50, capture_file=capture_file)
    protocol.connection_made(transport)

    # Start directly in input report 0x30 mode
    asyncio.ensure_future(protocol.input_report_mode_0x30())

    return protocol, sock

