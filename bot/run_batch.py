# bot/run_batch.py
import subprocess
import sys
import time
import os
from dotenv import load_dotenv
from twilio.rest import Client

TWILIO_ACCOUNT_SID = os.environ["TWILIO_ACCOUNT_SID"]
TWILIO_AUTH_TOKEN = os.environ["TWILIO_AUTH_TOKEN"]
client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

SCENARIOS_TO_RUN = [
    "schedule_appointment",
    "schedule_followup",
    "reschedule_appointment",
    "cancel_appointment",
    "refill_simple",
    "refill_unsure_name",
    "ask_office_hours",
    "ask_location",
    "ask_insurance",
    "edge_interruption",
    "edge_unclear_request",
    "edge_out_of_scope",
]

COOLDOWN_AFTER_CALL = 15  # extra buffer for recording/transcript callbacks to finish
POLL_INTERVAL = 5
MAX_WAIT_SECONDS = 300  # safety ceiling, matches your MAX_CALL_SECONDS + margin

DONE_STATUSES = {"completed", "busy", "failed", "no-answer", "canceled"}


def wait_for_call_to_finish(call_sid):
    waited = 0
    while waited < MAX_WAIT_SECONDS:
        call = client.calls(call_sid).fetch()
        print(f"  Call status: {call.status}", flush=True)
        if call.status in DONE_STATUSES:
            return call.status
        time.sleep(POLL_INTERVAL)
        waited += POLL_INTERVAL
    print("  Timed out waiting for call to finish", flush=True)
    return "timeout"

for scenario in SCENARIOS_TO_RUN:
    print(f"\n=== Starting call: {scenario} ===")
    result = subprocess.run(
        [sys.executable, "-m", "bot.call", scenario],
        capture_output=True, text=True,
    )
    print(result.stdout)

    # Pull the call SID out of call.py's printed output
    sid_line = [l for l in result.stdout.splitlines() if "SID:" in l]
    if not sid_line:
        print("  Could not find call SID in output, skipping wait")
        continue
    call_sid = sid_line[0].split("SID:")[-1].strip()

    status = wait_for_call_to_finish(call_sid)
    print(f"=== Call {scenario} finished with status: {status} ===")
    print(f"=== Cooling down {COOLDOWN_AFTER_CALL}s before next call ===")
    time.sleep(COOLDOWN_AFTER_CALL)