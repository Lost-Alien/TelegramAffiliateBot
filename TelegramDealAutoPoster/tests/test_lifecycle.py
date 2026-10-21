import asyncio

from lifecycle import run_services


def test_service_stop_disconnects_telegram_and_finishes_monitor():
    async def exercise():
        closed = asyncio.Event()
        stop = asyncio.Event()

        class Client:
            async def run_until_disconnected(self):
                await closed.wait()

            async def disconnect(self):
                closed.set()

        class Server:
            should_exit = False

            async def serve(self):
                while not self.should_exit:
                    await asyncio.sleep(0)

        server = Server()
        operation = asyncio.create_task(run_services(Client(), server, stop))
        await asyncio.sleep(0)
        stop.set()
        await asyncio.wait_for(operation, 1)
        assert closed.is_set()
        assert server.should_exit

    asyncio.run(exercise())


def test_monitor_failure_still_disconnects_telegram():
    async def exercise():
        closed = asyncio.Event()

        class Client:
            async def run_until_disconnected(self):
                await closed.wait()

            async def disconnect(self):
                closed.set()

        class Server:
            should_exit = False

            async def serve(self):
                raise RuntimeError("monitor failed")

        try:
            await run_services(Client(), Server(), asyncio.Event())
        except RuntimeError as error:
            assert str(error) == "monitor failed"
        else:
            assert False, "monitor error must reach the supervisor"
        assert closed.is_set()

    asyncio.run(exercise())


def test_stuck_monitor_cleanup_does_not_turn_requested_stop_into_failure(monkeypatch):
    actual_wait_for = asyncio.wait_for

    async def wait_for(awaitable, timeout):
        if timeout == 5:
            awaitable.cancel()
            raise asyncio.TimeoutError
        return await actual_wait_for(awaitable, timeout)

    monkeypatch.setattr(asyncio, "wait_for", wait_for)

    async def exercise():
        closed = asyncio.Event()
        stop = asyncio.Event()

        class Client:
            async def run_until_disconnected(self):
                await closed.wait()

            async def disconnect(self):
                closed.set()

        class Server:
            should_exit = False

            async def serve(self):
                await asyncio.Event().wait()

        operation = asyncio.create_task(run_services(Client(), Server(), stop))
        await asyncio.sleep(0)
        stop.set()
        await actual_wait_for(operation, 1)
        assert closed.is_set()

    asyncio.run(exercise())
