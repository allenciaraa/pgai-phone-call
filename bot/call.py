import os
from dotenv import load_dotenv
from twilio.rest import Client

load_dotenv()

TWILIO_ACCOUNT_SID = os.environ["TWILIO_ACCOUNT_SID"]
TWILIO_AUTH_TOKEN = os.environ["TWILIO_AUTH_TOKEN"]
TWILIO_PHONE_NUM = os.environ["TWILIO_PHONE_NUM"]
PUBLIC_SERVER_URL = os.environ["PUBLIC_SERVER_URL"]

TARGET_NUM = "+19518162016"

client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

call = client.calls.create(
    to=TARGET_NUM,
    from_=TWILIO_PHONE_NUM,
    url=f"{PUBLIC_SERVER_URL}/voice",
    record=True,
    recording_status_callback=f"{PUBLIC_SERVER_URL}/recording-status",
    recording_status_callback_event=["completed"],
)

print(f"CALL STARTED -- SID: {call.sid}")