import os
import sys
from dotenv import load_dotenv
from twilio.rest import Client
from bot.scenarios import SCENARIOS_BY_NAME

load_dotenv()

TWILIO_ACCOUNT_SID = os.environ["TWILIO_ACCOUNT_SID"]
TWILIO_AUTH_TOKEN = os.environ["TWILIO_AUTH_TOKEN"]
TWILIO_PHONE_NUM = os.environ["TWILIO_PHONE_NUM"]
PUBLIC_SERVER_URL = os.environ["PUBLIC_SERVER_URL"]

TARGET_NUM = "+18054398008"

SCENARIO_NAME = sys.argv[1] if len(sys.argv) > 1 else "schedule_appointment"

if SCENARIO_NAME not in SCENARIOS_BY_NAME:
    print(f"Unknown scenario: {SCENARIO_NAME}")
    print(f"Available: {list(SCENARIOS_BY_NAME.keys())}")
    sys.exit(1)

client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

call = client.calls.create(
    to=TARGET_NUM,
    from_=TWILIO_PHONE_NUM,
    url=f"{PUBLIC_SERVER_URL}/voice?scenario={SCENARIO_NAME}",
    record=True,
    recording_status_callback=f"{PUBLIC_SERVER_URL}/recording-status",
    recording_status_callback_event=["completed"],
)

print(f"CALL STARTED -- Scenario: {SCENARIO_NAME} -- SID: {call.sid}")