from fastapi import FastAPI
from fastapi.responses import Response

app = FastAPI()

@app.post("/voice")
async def voice():
    twiml = """<?xml version="1.0" encoding="UTF-8"?>
        <Response>
            <Say>Hello world! This is a voice endpoint test.</Say>
        </Response>
    """
    return Response(content=twiml, media_type="application/xml")

@app.get("/")
async def test():
    return {"status": "ok"}