import inspect
import logging
import asyncio

from aioconsole import ainput
from threading import Thread
from time import sleep
from joycontrol.controller_state import ControllerState, button_push
from queue import Queue
import socketserver
logger = logging.getLogger(__name__)
queue = Queue(10)

class Server(socketserver.TCPServer):
    allow_reuse_address = True

class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        while True:
            self.data = self.rfile.readline().strip()
            queue.put(self.data.decode())
            self.wfile.write(self.data.upper())

def serverThread():
    with Server(('0.0.0.0', 8888), Handler) as server:
        server.serve_forever()

class NetController:

    def __init__(self, controller_state: ControllerState):
        self.controller_state = controller_state
    
    async def run(self):
        await self.controller_state.connect()
        t = Thread(target=serverThread, daemon=True)
        t.start()
        while True:
            await asyncio.sleep(0.3)
            if not queue.empty():
                cmd = queue.get()
                print(f'Got: {cmd}')
                cmd,*args = cmd.split(' ')
                if cmd == 'press':
                    self.controller_state.button_state.set_button(args[0])
                    await self.controller_state.send()
                elif  cmd == 'release':
                    self.controller_state.button_state.set_button(args[0],False)
                    await self.controller_state.send()
                elif cmd == 'click':
                    await button_push(self.controller_state,args[0])