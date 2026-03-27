import asyncio
from collections.abc import AsyncIterator

import anyio
import pytest
from sse_starlette import EventSourceResponse, ServerSentEvent

from park_it.services.sse_handler import SSEHandler


def _encoded(event: ServerSentEvent) -> str:
    return event.encode().decode()


async def _next_event(stream: AsyncIterator[ServerSentEvent]) -> ServerSentEvent:
    return await anext(stream)


@pytest.mark.anyio
async def test_subscribe_and_publish_delivers_payload():
    handler = SSEHandler()
    subscriber = await handler.subscribe()

    delivered = await handler.publish("<div>ok</div>")
    message = subscriber.get_nowait()

    assert delivered == 1
    assert isinstance(message, ServerSentEvent)
    assert _encoded(message) == "event: message\r\ndata: <div>ok</div>\r\n\r\n"


@pytest.mark.anyio
async def test_publish_multiline_data_is_split_per_sse_line():
    handler = SSEHandler()
    subscriber = await handler.subscribe()

    await handler.publish("line-1\nline-2", event="status")
    message = subscriber.get_nowait()

    assert isinstance(message, ServerSentEvent)
    assert _encoded(message) == "event: status\r\ndata: line-1\r\ndata: line-2\r\n\r\n"


@pytest.mark.anyio
async def test_publish_drops_stale_message_when_queue_is_full():
    handler = SSEHandler(queue_maxsize=1)
    subscriber = await handler.subscribe()

    await handler.publish("first")
    await handler.publish("second")
    message = subscriber.get_nowait()

    assert isinstance(message, ServerSentEvent)
    assert _encoded(message) == "event: message\r\ndata: second\r\n\r\n"


@pytest.mark.anyio
async def test_stream_stops_after_shutdown_signal():
    handler = SSEHandler()
    stream = handler.stream(shutdown_event=anyio.Event())
    next_item = asyncio.create_task(_next_event(stream))

    await asyncio.sleep(0)
    assert handler.subscriber_count == 1

    await handler.shutdown()
    with pytest.raises(StopAsyncIteration):
        await next_item
    assert handler.subscriber_count == 0


@pytest.mark.anyio
async def test_stream_stops_after_sse_starlette_shutdown_event():
    handler = SSEHandler()
    shutdown_event = anyio.Event()
    stream = handler.stream(shutdown_event=shutdown_event)
    next_item = asyncio.create_task(_next_event(stream))

    await asyncio.sleep(0)
    assert handler.subscriber_count == 1

    shutdown_event.set()
    with pytest.raises(StopAsyncIteration):
        await next_item
    assert handler.subscriber_count == 0


def test_response_returns_event_source_response():
    handler = SSEHandler()

    response = handler.response(ping_seconds=1)

    assert isinstance(response, EventSourceResponse)
    assert getattr(response, "_shutdown_grace_period") == 0.5


@pytest.mark.anyio
async def test_publish_returns_zero_after_shutdown():
    handler = SSEHandler()
    await handler.shutdown()

    delivered = await handler.publish("ignored")

    assert delivered == 0
