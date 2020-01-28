import asyncio
import logging
import re

logger = logging.getLogger(__name__)


async def run_system_command(cmd):
    proc = await asyncio.create_subprocess_shell(
        cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE)

    stdout, stderr = await proc.communicate()

    logger.debug(f'[{cmd!r} exited with {proc.returncode}]')
    if stdout:
        logger.debug(f'[stdout]\n{stdout.decode()}')
    if stderr:
        logger.debug(f'[stderr]\n{stderr.decode()}')

    return proc.returncode, stdout, stderr

"""
async def get_bt_mac_address(dev=0):
    ret, stdout, stderr = await run_system_command(f'hciconfig hci{dev}')
    # TODO: Process error handling

    match = re.search(r'BD Address: (?P<mac>\w\w:\w\w:\w\w:\w\w:\w\w:\w\w)', stdout.decode('UTF-8'))
    if match:
        return list(map(lambda x: int(x, 16), match.group('mac').split(':')))
    else:
        raise ValueError(f'BD Address not found in "{stdout}"')
"""
