"""Bridge synchronous Blender I/O without blocking the MCP event loop."""
from functools import partial
from functools import wraps

import anyio


async def run_blocking(function, *args, **kwargs):
    # Do not abandon a worker on cancellation: it must drain the response and
    # release the socket lock before a subsequent command can use the stream.
    return await anyio.to_thread.run_sync(partial(function, *args, **kwargs))


def io_registration(register, *args, **kwargs):
    """Register a sync tool/resource as async, retaining its public sync API."""
    def decorate(function):
        @wraps(function)
        async def threaded(**arguments):
            return await run_blocking(function, **arguments)
        register(*args, **kwargs)(threaded)
        return function
    return decorate
