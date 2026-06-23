# Bug Report — PGAI Voice Agent

Found across 12 test calls placed to the PGAI test line (+1-805-439-8008), covering scheduling, rescheduling, cancellation, refills, office hours, location, insurance, and several edge-case scenarios. Full transcripts and audio recordings for every call referenced here are in `calls/transcripts/` and `calls/recordings/`, named by Twilio Call SID.

---

## Bug 1: Identity verification fails even when all information is provided correctly and confirmed

**Severity:** Critical

**Calls:** `CA63dc1eb81ac03eda046f7500795f8889`, `CAba8698afd516afc497cbbc23d4e15d3e`, `CAe9b72d307dfc6d3c37c5297acfaf83dc`, `CAc723698c7d23226f0964292eae530e40`, `CAb753b3c9c3ddc1204a292461451493df`, `CA52354a2830450856d5dfca805d073855`, `CA783b6d8cbd602adfe31ce13dcbf2984b`, `CA3fb49ea2c750e5125cf9d6ca7eae9342` — 8 of 12 calls.

**Details:** In every affected call, the agent asks for the caller's name and date of birth, the caller provides it, the agent repeats it back correctly, and the caller explicitly confirms it's correct. Despite this, the agent then says some version of:

> "Something's not right. I can't proceed further right now, but I can make sure our clinic support team follows up with you."

or

> "I'm not able to verify the chart right now. I can't proceed further at this moment."

This happens regardless of whether the caller is a returning patient with a (fabricated-but-consistent) phone number on file, or an explicitly new patient with no record to look up (see `CA3fb49ea2c750e5125cf9d6ca7eae9342`, where the caller states up front "I'm actually a new patient, so I don't think I'd have a record on file yet" — the agent still fails verification on a caller it should never have expected to find a record for).

**Why it matters:** This is the dominant failure mode across the entire test batch (8 of 12 calls). It means the overwhelming majority of real patients calling this line — for routine, simple requests — cannot get past identity verification at all, regardless of how correctly and patiently they answer the agent's questions. This isn't an edge case; it's the main path.

**Example:** `CA63dc1eb81ac03eda046f7500795f8889`, full exchange:

```
Caller: Please confirm those two details.
Bot: Yeah, that's correct.
Caller: Something's not right.
Caller: I can't proceed further right now, but I can make sure our clinic support team follows up with you.
```

---

## Bug 2: Agent claims to be "connecting you to a representative," then immediately disconnects the call

**Severity:** Critical

**Calls:** `CAba8698afd516afc497cbbc23d4e15d3e`, `CAe9b72d307dfc6d3c37c5297acfaf83dc`, `CAc723698c7d23226f0964292eae530e40`, `CAb753b3c9c3ddc1204a292461451493df`, `CA52354a2830450856d5dfca805d073855`, `CA3fb49ea2c750e5125cf9d6ca7eae9342` — 6 of 12 calls.

**Details:** After failing to help (often following Bug 1), the agent says "Connecting you to a representative. Please wait." The very next thing the caller hears is a generic system message — "Hello. You've reached the Pretty Good AI test line. Goodbye." — and the call ends. No actual transfer or human handoff occurs.

**Why it matters:** This actively misleads the caller about what's happening. A real patient who has just been told to wait for a human, and is then abruptly hung up on, is a worse experience than simply being told upfront the agent can't help. This also means there is currently no working escalation path on this line at all — every "transfer" observed in testing resulted in a dropped call, not a handoff.

**Example:** `CAb753b3c9c3ddc1204a292461451493df`:

```
Caller: Connecting you to a representative.
Caller: Please wait.
Caller: Hello. You've reached the Pretty Good AI test line.
Caller: Goodbye.
Bot: Wait — I didn't get to do what I called about. I need to cancel an appointment.
```

---
