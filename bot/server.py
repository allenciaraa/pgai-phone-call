import os
import json
import httpx
from fastapi import FastAPI
from fastapi import WebSocket
from fastapi.responses import Response
from dotenv import load_dotenv
from pipecat.serializers.twilio import TwilioFrameSerializer
from pipecat.transports.websocket.fastapi import (
    FastAPIWebsocketTransport,
    FastAPIWebsocketParams,
)
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineWorker, PipelineParams
from pipecat.workers.runner import WorkerRunner
from pipecat.observers.base_observer import BaseObserver
from pipecat.services.cartesia.tts import CartesiaTTSService
from pipecat.frames.frames import TTSSpeakFrame
from pipecat.frames.frames import TranscriptionFrame
from pipecat.frames.frames import TextFrame
from pipecat.services.deepgram.stt import DeepgramSTTService
from pipecat.services.anthropic.llm import AnthropicLLMService
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import LLMContextAggregatorPair

load_dotenv()
PUBLIC_SERVER_URL = os.environ["PUBLIC_SERVER_URL"]
TWILIO_ACCOUNT_SID = os.environ["TWILIO_ACCOUNT_SID"]
TWILIO_AUTH_TOKEN = os.environ["TWILIO_AUTH_TOKEN"]

class TranscriptLogger(BaseObserver):
    def __init__(self, stt_processor):
        super().__init__()
        self.stt_processor = stt_processor

    async def on_push_frame(self, data):
        if isinstance(data.frame, TranscriptionFrame) and data.source is self.stt_processor:
            print(f"HEARD: {data.frame.text}", flush=True)

class ResponseLogger(BaseObserver):
    def __init__(self, llm_processor):
        super().__init__()
        self.llm_processor = llm_processor

    async def on_push_frame(self, data):
        if isinstance(data.frame, TextFrame) and data.source is self.llm_processor:
            print(f"LLM SAID: {data.frame.text}", flush=True)

app = FastAPI()

@app.post("/voice")
async def voice():
    stream_url = PUBLIC_SERVER_URL.replace("https://", "wss://")
    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
        <Response>
            <Connect>
                <Stream url="{stream_url}/media-stream" />
            </Connect>
        </Response>
    """
    return Response(content=twiml, media_type="application/xml")

@app.websocket("/media-stream")
async def media_stream(websocket: WebSocket):
    await websocket.accept()

    start_data = websocket.iter_text()
    await start_data.__anext__()  # 'connected' message, discard
    call_data = await start_data.__anext__()  # 'start' message, keep for IDs

    call_data = json.loads(call_data)
    stream_sid = call_data["start"]["streamSid"]
    call_sid = call_data["start"]["callSid"]

    serializer = TwilioFrameSerializer(
        stream_sid=stream_sid,
        call_sid=call_sid,
        account_sid=TWILIO_ACCOUNT_SID,
        auth_token=TWILIO_AUTH_TOKEN,
    )

    transport = FastAPIWebsocketTransport(
        websocket=websocket,
        params=FastAPIWebsocketParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            add_wav_header=False,
            serializer=serializer,
        ),
    )

    stt = DeepgramSTTService(
        api_key=os.environ["DEEPGRAM_API_KEY"],
    )

    llm = AnthropicLLMService(
        api_key=os.environ["ANTHROPIC_API_KEY"],
        model="claude-sonnet-4-6",
    )

    tts = CartesiaTTSService(
        api_key=os.environ["CARTESIA_API_KEY"],
        voice_id="f786b574-daa5-4673-aa0c-cbe3e8534c02",
    )

    context = LLMContext(
        messages=[
            {
                "role": "system",
                "content": "You are a helpful assistant having a phone conversation. Keep responses brief, 1-2 sentences.",
            }
        ]
    )

    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(context)

    pipeline = Pipeline([
        transport.input(),
        stt,
        user_aggregator,
        llm,
        tts,
        transport.output(),
        assistant_aggregator,
    ])

    worker = PipelineWorker(
        pipeline,
        enable_rtvi=False,
        params=PipelineParams(
            audio_in_sample_rate=8000,
            audio_out_sample_rate=8000,
        ),
        observers=[TranscriptLogger(stt), ResponseLogger(llm)],
    )
    runner = WorkerRunner()

    @worker.event_handler("on_pipeline_finished")
    async def on_pipeline_finished(worker, frame):
        print(f"Call ended: {call_sid}")

    @worker.event_handler("on_pipeline_error")
    async def on_pipeline_error(worker, frame):
        print(f"Pipeline error on call {call_sid}: {frame}")

    try:
        await runner.run(worker)
    except Exception as e:
        import traceback
        print(f"Pipeline crashed on call {call_sid}: {e}")
        traceback.print_exc()

@app.get("/")
async def test():
    return {"status": "ok"}