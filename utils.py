import asyncio
import logging

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

    return proc.returncode
