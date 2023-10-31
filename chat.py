from asyncio import Event, Queue, gather
from enum import Enum

import msgspec
from httpx import HTTPError
from pydantic import BaseModel, Field, ValidationError
from starlite import Dependency, Response, WebSocket, post, websocket

from client import client, inject_sk


class MessageType(str, Enum):
    user = "user"
    system = "system"
    assistant = "assistant"


class Message(BaseModel):
    role: MessageType
    content: str


class ChatIn(BaseModel):
    messages: list[Message]
    temperature: int | float = Field(1, ge=0, le=2)
    top_p: int | float = Field(1, ge=0, le=2)
    n: int = Field(1, ge=1)


@post("/chat", dependencies=inject_sk)
async def chat(data: ChatIn, bearer: dict = Dependency()) -> Response:
    try:
        body = {"model": "gpt-3.5-turbo", **data.dict()}
        while True:
            try:
                res = await client.post("/chat/completions", json=body, headers=bearer)
                return Response(res.content, status_code=res.status_code)
            except HTTPError as err:
                print(err)
    except Exception as err:
        print(err)


@websocket("/chat/ws", dependencies=inject_sk)
async def chat_streaming(socket: WebSocket, bearer: dict = Dependency()) -> None:
    await socket.accept()
    try:
        data = await socket.receive_json()
        ChatIn.validate(data)
        body = {"model": "gpt-3.5-turbo", "stream": True, **data}
        while True:
            try:
                async with client.stream("POST", "/chat/completions", json=body, headers=bearer) as res:
                    async for line in res.aiter_lines():
                        json: str = line.lstrip("data: ").rstrip("\n")
                        if json and json != "[DONE]":
                            await socket.send_text(json)
                    break

            except HTTPError as err:
                print(err)
    except ValidationError as err:
        await socket.send_json(err.json())
    finally:
        await socket.close()


@websocket("/chat/ws/reform", dependencies=inject_sk)
async def chat_streaming_reformed(socket: WebSocket, bearer: dict = Dependency()) -> None:
    await socket.accept()
    try:
        data = await socket.receive_json()
        n: int = ChatIn(**data).n
        body = {"model": "gpt-3.5-turbo", "stream": True, **data}

        results_queue = Queue()
        new_result_event = Event()
        running = True

        async def receive_from_openai():
            nonlocal running
            while running:
                try:
                    async with client.stream("POST", "/chat/completions", json=body, headers=bearer) as res:
                        async for line in res.aiter_lines():
                            json: str = line.lstrip("data: ").rstrip("\n")
                            if json and json != "[DONE]":
                                await results_queue.put(json)
                                new_result_event.set()

                    running = False
                    new_result_event.set()

                except HTTPError as e:
                    print(e)

        async def send_to_client():
            nonlocal running
            while running:
                await new_result_event.wait()
                messages = []
                while not results_queue.empty():
                    messages.append(await results_queue.get())
                new_result_event.clear()

                if not messages:
                    return

                if len(messages) == 1:
                    await socket.send_text(messages[0])
                    continue

                contents = [[] for _ in range(n)]
                finish_reasons = [None] * n

                msg: dict = {}
                for json in messages:
                    msg = msgspec.json.decode(json)
                    choice = msg["choices"][0]
                    i, delta = choice["index"], choice["delta"]
                    if "content" in delta:
                        contents[i].append(delta["content"])
                    else:
                        await socket.send_text(json)  # head response
                    finish_reasons[i] = choice["finish_reason"]

                for i in range(n):
                    if deltas := contents[i]:
                        if len(deltas) > 1:
                            print(len(deltas))
                        await socket.send_json({**msg, "choices": [{
                            "delta": {"content": "".join(deltas)},
                            "index": i,
                            "finish_reason": finish_reasons[i],
                        }]})

        await gather(receive_from_openai(), send_to_client())

    except ValidationError as err:
        await socket.send_json(err.json())
    finally:
        await socket.close()
