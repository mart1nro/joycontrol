
delay_override = False
delay = 1/15

async def debug(*args):
    global delay_override
    global delay
    if len(args) > 0:
        delay_override = True
        delay = 1/float(args[0])

def get_delay(old):
    return delay if delay_override else old
