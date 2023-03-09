from enum import Enum

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
