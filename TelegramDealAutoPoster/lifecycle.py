"""Own shutdown for the Telegram connection and embedded monitor together."""
import asyncio
import signal


async def run_services(client, server, stop=None):
    loop = asyncio.get_running_loop()
    installed = []
    if stop is None:
        stop = asyncio.Event()
        for signum in (signal.SIGTERM, signal.SIGINT):
            try:
                loop.add_signal_handler(signum, stop.set)
                installed.append(signum)
            except NotImplementedError:
                signal.signal(signum, lambda *_: loop.call_soon_threadsafe(stop.set))

    tasks = [asyncio.create_task(server.serve()),
             asyncio.create_task(client.run_until_disconnected()),
             asyncio.create_task(stop.wait())]
    try:
        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            task.result()
    finally:
        server.should_exit = True
        try:
            await asyncio.wait_for(client.disconnect(), timeout=8)
            await asyncio.wait_for(asyncio.gather(*tasks[:2], return_exceptions=True), timeout=8)
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            for signum in installed:
                loop.remove_signal_handler(signum)
