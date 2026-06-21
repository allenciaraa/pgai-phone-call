import os
import json
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
from pipecat.pipeline.worker import PipelineWorker
from pipecat.workers.runner import WorkerRunner
from pipecat.observers.base_observer import BaseObserver
from pipecat.services.cartesia.tts import CartesiaTTSService

load_dotenv()
PUBLIC_SERVER_URL = os.environ["PUBLIC_SERVER_URL"]
TWILIO_ACCOUNT_SID = os.environ["TWILIO_ACCOUNT_SID"]
TWILIO_AUTH_TOKEN = os.environ["TWILIO_AUTH_TOKEN"]

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
    await start_data.__anext__() # 'connected' message, throw it out
    call_data = await start_data.__anext__() # 'start' message, keep for IDs

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

    tts = CartesiaTTSService(
        api_key=os.environ["CARTESIA_API_KEY"],
        voice_id="f786b574-daa5-4673-aa0c-cbe3e8534c02",
    )

    pipeline = Pipeline([
        transport.input(),
        tts,
        transport.output(),
    ])

    class FrameLogger(BaseObserver):
        async def on_push_frame(self, data):
            print(f"FRAME: {type(data.frame).__name__}", flush=True)

    worker = PipelineWorker(pipeline, enable_rtvi=False, observers=[FrameLogger()])
    runner = WorkerRunner()

    @worker.event_handler("on_pipeline_finished")
    async def on_pipeline_finished(worker, frame):
        print(f"Pipeline finished. Frame type: {type(frame).__name__}")

    @worker.event_handler("on_pipeline_error")
    async def on_pipeline_error(worker, frame):
        print(f"Pipeline ERROR: {frame}")

    @worker.event_handler("on_pipeline_started")
    async def on_pipeline_started(worker, frame):
        from pipecat.frames.frames import TTSSpeakFrame
        await worker.queue_frame(TTSSpeakFrame(text="Hello, this is a test of the output audio."))


    try:
        await runner.run(worker)
    except Exception as e:
        import traceback
        print(f"Pipeline crashed: {e}")
        traceback.print_exc()

@app.get("/")
async def test():
    return {"status": "ok"}