from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from collections.abc import AsyncIterable
from dataclasses import dataclass
from typing import Generic, Literal, TypeVar, Union

from livekit import rtc

from ..types import NOT_GIVEN, NotGivenOr
from .chat_context import ChatContext, FunctionCall
from .tool_context import FunctionTool, ToolChoice, ToolContext


@dataclass
class InputSpeechStartedEvent:
    pass


@dataclass
class InputSpeechStoppedEvent:
    user_transcription_enabled: bool


@dataclass
class MessageGeneration:
    message_id: str
    text_stream: AsyncIterable[str]  # could be io.TimedString
    audio_stream: AsyncIterable[rtc.AudioFrame]


@dataclass
class GenerationCreatedEvent:
    message_stream: AsyncIterable[MessageGeneration]
    function_stream: AsyncIterable[FunctionCall]
    user_initiated: bool
    """True if the message was generated by the user using generate_reply()"""


@dataclass
class ErrorEvent:
    type: str
    message: str


@dataclass
class RealtimeCapabilities:
    message_truncation: bool
    turn_detection: bool
    user_transcription: bool


class RealtimeError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)


class RealtimeModel:
    def __init__(self, *, capabilities: RealtimeCapabilities) -> None:
        self._capabilities = capabilities

    @property
    def capabilities(self) -> RealtimeCapabilities:
        return self._capabilities

    @abstractmethod
    def session(self) -> RealtimeSession: ...

    @abstractmethod
    async def aclose(self) -> None: ...


EventTypes = Literal[
    "input_speech_started",  # serverside VAD (also used for interruptions)
    "input_speech_stopped",  # serverside VAD
    "input_audio_transcription_completed",
    "generation_created",
    "error",
]

TEvent = TypeVar("TEvent")


@dataclass
class InputTranscriptionCompleted:
    item_id: str
    """id of the item"""
    transcript: str
    """transcript of the input audio"""


class RealtimeSession(ABC, rtc.EventEmitter[Union[EventTypes, TEvent]], Generic[TEvent]):
    def __init__(self, realtime_model: RealtimeModel) -> None:
        super().__init__()
        self._realtime_model = realtime_model

    @property
    def realtime_model(self) -> RealtimeModel:
        return self._realtime_model

    @property
    @abstractmethod
    def chat_ctx(self) -> ChatContext: ...

    @property
    @abstractmethod
    def tools(self) -> ToolContext: ...

    @abstractmethod
    async def update_instructions(self, instructions: str) -> None: ...

    @abstractmethod
    async def update_chat_ctx(
        self, chat_ctx: ChatContext
    ) -> None: ...  # can raise RealtimeError on Timeout

    @abstractmethod
    async def update_tools(self, tools: list[FunctionTool]) -> None: ...

    @abstractmethod
    def update_options(self, *, tool_choice: NotGivenOr[ToolChoice | None] = NOT_GIVEN) -> None: ...

    @abstractmethod
    def push_audio(self, frame: rtc.AudioFrame) -> None: ...

    @abstractmethod
    def generate_reply(
        self,
        *,
        instructions: NotGivenOr[str] = NOT_GIVEN,
    ) -> asyncio.Future[GenerationCreatedEvent]: ...  # can raise RealtimeError on Timeout

    # commit the input audio buffer to the server
    @abstractmethod
    def commit_input_audio(self) -> None: ...

    # cancel the current generation (do nothing if no generation is in progress)
    @abstractmethod
    def interrupt(self) -> None: ...

    # message_id is the ID of the message to truncate (inside the ChatCtx)
    @abstractmethod
    def truncate(self, *, message_id: str, audio_end_ms: int) -> None: ...

    @abstractmethod
    async def aclose(self) -> None: ...
