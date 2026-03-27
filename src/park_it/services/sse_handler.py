from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import anyio
from sse_starlette import EventSourceResponse, ServerSentEvent


class SSEHandler:
    """In-memory fan-out for server-sent events across connected clients.

    Typical lifecycle:
    1. A route returns `response()`, which creates one `EventSourceResponse`.
    2. That response consumes `stream(...)` for a single connected client.
    3. `publish(...)` broadcasts one structured SSE event to every subscriber.
    4. `shutdown()` or server termination causes each stream to exit cleanly.
    """

    def __init__(self, queue_maxsize: int = 20) -> None:
        """Create an SSE broker with bounded per-client queues.

        Args:
            queue_maxsize: Max pending messages stored per connected client.
                Lower values favor "latest state" delivery over full history.
        """
        # Each subscriber gets its own bounded queue of ServerSentEvent objects.
        # Keeping already-structured events here means the rest of the app does not
        # need to know about SSE framing details.
        self._queue_maxsize = queue_maxsize
        self._subscribers: set[asyncio.Queue[ServerSentEvent | object]] = set()
        # Guard subscribe/unsubscribe/publish snapshot operations.
        self._lock = asyncio.Lock()
        # Once closed, new subscribers/events are rejected and existing streams
        # should wind down promptly.
        self._closed = False
        self._stop_signal = object()

    @property
    def subscriber_count(self) -> int:
        """Return the number of currently connected SSE subscribers."""
        return len(self._subscribers)

    async def subscribe(self) -> asyncio.Queue[ServerSentEvent | object]:
        """Register one subscriber and return its message queue."""
        queue: asyncio.Queue[ServerSentEvent | object] = asyncio.Queue(
            maxsize=self._queue_maxsize
        )
        async with self._lock:
            if self._closed:
                return queue
            self._subscribers.add(queue)
        return queue

    async def unsubscribe(self, queue: asyncio.Queue[ServerSentEvent | object]) -> None:
        """Remove a subscriber queue so it no longer receives broadcasts."""
        async with self._lock:
            self._subscribers.discard(queue)

    async def publish(self, data: str, event: str = "message") -> int:
        """Broadcast one SSE event to every active subscriber.

        Args:
            data: Event payload (often rendered HTML for HTMX OOB swaps).
            event: SSE event name clients listen for (`message` by default).

        Returns:
            Number of subscribers this publish attempted to deliver to.
        """
        payload = ServerSentEvent(data=data, event=event)
        async with self._lock:
            if self._closed:
                return 0
            # Publish against a stable snapshot so lock hold time stays short.
            subscribers = tuple(self._subscribers)

        for queue in subscribers:
            if queue.full():
                try:
                    # Drop the oldest queued event so the newest state can flow
                    # through. For this app, current state matters more than history.
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass

            try:
                queue.put_nowait(payload)
            except asyncio.QueueFull:
                # If a queue remains full after dropping one stale item, skip this
                # tick rather than blocking the publisher.
                continue

        return len(subscribers)

    async def shutdown(self) -> None:
        """Tell all active streams to stop consuming new events.

        `EventSourceResponse` already listens for server shutdown and client disconnect,
        but keeping this explicit close path is still useful for app teardown and tests.
        """
        async with self._lock:
            self._closed = True
            subscribers = tuple(self._subscribers)

        for queue in subscribers:
            if queue.full():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass

            try:
                queue.put_nowait(self._stop_signal)
            except asyncio.QueueFull:
                # If a queue remains full, the response will still terminate on
                # disconnect or cancellation from sse-starlette.
                continue

    async def stream(
        self, shutdown_event: anyio.Event
    ) -> AsyncIterator[ServerSentEvent]:
        """Yield events for one connected SSE client.

        sse-starlette now owns:
        - HTTP disconnect detection
        - periodic ping comments
        - Uvicorn shutdown detection

        This generator focuses on queue fan-out only. A per-response shutdown event is
        passed in so the library can signal us before force-cancelling the response.
        That gives the generator a chance to exit cooperatively.
        """
        queue = await self.subscribe()
        if self._closed:
            return

        shutdown_task = asyncio.create_task(shutdown_event.wait())

        try:
            while True:
                if self._closed:
                    break

                queue_task = asyncio.create_task(queue.get())

                try:
                    done, _ = await asyncio.wait(
                        {queue_task, shutdown_task},
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                finally:
                    if not queue_task.done():
                        queue_task.cancel()

                if shutdown_task in done:
                    break

                item = queue_task.result()
                if item is self._stop_signal:
                    break

                assert isinstance(item, ServerSentEvent)
                yield item
        finally:
            if not shutdown_task.done():
                shutdown_task.cancel()
            # Always unsubscribe, even if the client disconnects or the response task
            # is cancelled during shutdown.
            await self.unsubscribe(queue)

    def response(
        self,
        ping_seconds: int = 15,
        shutdown_grace_period: float = 0.5,
    ) -> EventSourceResponse:
        """Create the SSE response object for one connecting client.

        The response gets a dedicated shutdown event shared with `stream(...)`. When
        sse-starlette observes Uvicorn shutdown, it sets that event before cancelling
        the response task group, which lets our generator stop cleanly first. Keep the
        grace period non-zero so `_stream_response()` can send the terminating
        `more_body=False` frame before the task group is cancelled.
        """
        shutdown_event = anyio.Event()
        return EventSourceResponse(
            self.stream(shutdown_event=shutdown_event),
            ping=ping_seconds,
            headers={
                # Disable proxy buffering/caching so HTMX receives updates promptly.
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
            shutdown_event=shutdown_event,
            shutdown_grace_period=shutdown_grace_period,
        )
