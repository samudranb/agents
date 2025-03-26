import logging

from dotenv import load_dotenv

from livekit.agents import (
    Agent,
    AgentSession,
    JobContext,
    JobProcess,
    RoomInputOptions,
    RoomOutputOptions,
    RunContext,
    WorkerOptions,
    cli,
    metrics,
)
from livekit.agents.llm import function_tool
from livekit.agents.voice import MetricsCollectedEvent
from livekit.plugins import cartesia, deepgram, openai, silero

# from livekit.plugins import noise_cancellation

logger = logging.getLogger("roomio-example")

load_dotenv()


class EchoAgent(Agent):
    def __init__(self) -> None:
        super().__init__(
            instructions="You are Echo.",
            stt=deepgram.STT(),
            llm=openai.LLM(model="gpt-4o-mini"),
            # Agents support both LLM and Realtime APIs
            # llm=openai.realtime.RealtimeModel(voice="echo"),
            tts=cartesia.TTS(),
        )

    async def on_enter(self):
        # when the agent is added to the session, it'll generate a reply
        # according to its instructions
        self.session.generate_reply()

    @function_tool
    async def transfer_to_alloy(self, context: RunContext):
        """Called when the user wants to be transferred to Alloy."""
        return AlloyAgent(), "Transferring you to Alloy."


class AlloyAgent(Agent):
    def __init__(self) -> None:
        super().__init__(
            instructions="You are Alloy.",
            llm=openai.realtime.RealtimeModel(voice="alloy"),
        )

    async def on_enter(self):
        self.session.generate_reply()

    @function_tool
    async def transfer_to_echo(self, context: RunContext):
        """Called when the user wants to be transferred to Echo."""
        return EchoAgent(), "Transferring you to Echo."


def prewarm(proc: JobProcess):
    proc.userdata["vad"] = silero.VAD.load()


async def entrypoint(ctx: JobContext):
    await ctx.connect()

    session = AgentSession(
        vad=ctx.proc.userdata["vad"],
    )

    # log metrics as they are emitted, and total usage after session is over
    usage_collector = metrics.UsageCollector()

    @session.on("metrics_collected")
    def _on_metrics_collected(ev: MetricsCollectedEvent):
        metrics.log_metrics(ev.metrics)
        usage_collector.collect(ev.metrics)

    async def log_usage():
        summary = usage_collector.get_summary()
        logger.info(f"Usage: ${summary}")

    ctx.add_shutdown_callback(log_usage)

    await session.start(
        agent=EchoAgent(),
        room=ctx.room,
        room_input_options=RoomInputOptions(
            # noise_cancellation=noise_cancellation.BVC(),
        ),
        room_output_options=RoomOutputOptions(transcription_enabled=True),
    )


if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint, prewarm_fnc=prewarm))
