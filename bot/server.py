import os
import json
import httpx
import asyncio
from fastapi import FastAPI
from fastapi import WebSocket
from fastapi import Request
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
from pipecat.services.deepgram.stt import DeepgramSTTService
from pipecat.services.anthropic.llm import AnthropicLLMService
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import LLMContextAggregatorPair
from pipecat.frames.frames import (
    TranscriptionFrame,
    TextFrame,
    LLMFullResponseStartFrame,
    LLMFullResponseEndFrame,
)
from bot.scenarios import SCENARIOS_BY_NAME

load_dotenv()
PUBLIC_SERVER_URL = os.environ["PUBLIC_SERVER_URL"]
TWILIO_ACCOUNT_SID = os.environ["TWILIO_ACCOUNT_SID"]
TWILIO_AUTH_TOKEN = os.environ["TWILIO_AUTH_TOKEN"]

class TranscriptSaver(BaseObserver):
    def __init__(self, stt_processor, llm_processor, call_sid):
        super().__init__()
        self.stt_processor = stt_processor
        self.llm_processor = llm_processor
        self.call_sid = call_sid
        self.lines = []
        self._bot_buffer = ""

    async def on_push_frame(self, data):
        if isinstance(data.frame, TranscriptionFrame) and data.source is self.stt_processor:
            self.lines.append(f"Caller: {data.frame.text}")
        elif data.source is self.llm_processor:
            if isinstance(data.frame, LLMFullResponseStartFrame):
                self._bot_buffer = ""
            elif isinstance(data.frame, TextFrame):
                self._bot_buffer += data.frame.text
            elif isinstance(data.frame, LLMFullResponseEndFrame):
                if self._bot_buffer:
                    self.lines.append(f"Bot: {self._bot_buffer}")
                self._bot_buffer = ""

    def save(self):
        os.makedirs("calls/transcripts", exist_ok=True)
        filepath = f"calls/transcripts/{self.call_sid}.txt"
        with open(filepath, "w") as f:
            f.write("\n".join(self.lines))
        print(f"Saved transcript: {filepath}", flush=True)

MAX_CALL_SECONDS = int(os.environ.get("MAX_CALL_SECONDS", 240))

async def enforce_max_duration(worker, call_sid):
    await asyncio.sleep(MAX_CALL_SECONDS)
    print(f"Call {call_sid} hit max duration ({MAX_CALL_SECONDS}s), forcing end", flush=True)
    await worker.cancel()


app = FastAPI()

@app.post("/voice")
async def voice(scenario: str = "schedule_appointment"):
    stream_url = PUBLIC_SERVER_URL.replace("https://", "wss://")
    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
        <Response>
            <Connect>
                <Stream url="{stream_url}/media-stream">
                    <Parameter name="scenario" value="{scenario}" />
                </Stream>
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
    custom_params = call_data["start"].get("customParameters", {})
    scenario_name = custom_params.get("scenario", "schedule_appointment")
    active_scenario = SCENARIOS_BY_NAME.get(scenario_name, SCENARIOS_BY_NAME["schedule_appointment"])
    print(f"Using scenario: {active_scenario['name']}", flush=True)

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
                "content": active_scenario["system_prompt"],
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
    transcript_saver = TranscriptSaver(stt, llm, call_sid)

    worker = PipelineWorker(
        pipeline,
        enable_rtvi=False,
        params=PipelineParams(audio_in_sample_rate=8000, audio_out_sample_rate=8000),
        observers=[transcript_saver],
    )
    runner = WorkerRunner()

    timeout_task = asyncio.create_task(enforce_max_duration(worker, call_sid))


    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        print(f"Client disconnected for call {call_sid}", flush=True)
        await worker.cancel()

    @worker.event_handler("on_pipeline_finished")
    async def on_pipeline_finished(worker, frame):
        print(f"Pipeline finished for call {call_sid} (frame: {type(frame).__name__})", flush=True)

    @worker.event_handler("on_pipeline_error")
    async def on_pipeline_error(worker, frame):
        print(f"Pipeline error on call {call_sid}: {frame}")

    try:
        await runner.run(worker)
        print(f"runner.run() returned normally for {call_sid}", flush=True)
    except Exception as e:
        import traceback
        print(f"Pipeline crashed on call {call_sid}: {e}")
        traceback.print_exc()
    finally:
        timeout_task.cancel()
        transcript_saver.save()
        print(f"Call ended: {call_sid}", flush=True)

@app.post("/recording-status")
async def recording_status(request: Request):
    form = await request.form()
    print(f"Recording callback received: {dict(form)}", flush=True)

    recording_url = form.get("RecordingUrl")
    call_sid = form.get("CallSid")

    if not recording_url:
        print("No RecordingUrl in callback, skipping download", flush=True)
        return {"status": "ignored"}
    
    mp3_url = f"{recording_url}.mp3"

    async with httpx.AsyncClient() as client:
        response = await client.get(
            mp3_url,
            auth=(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN),
        )

    os.makedirs("calls/recordings", exist_ok=True)
    filepath = f"calls/recordings/{call_sid}.mp3"
    with open(filepath, "wb") as f:
        f.write(response.content)

    print(f"Saved recording: {filepath}", flush=True)
    return {"status": "saved"}

@app.get("/")
async def test():
    return {"status": "ok"}