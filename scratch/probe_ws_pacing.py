"""Bare WebSocket subscribe pacing check. Server must be running on :8000.
Run: python scratch/probe_ws_pacing.py  (bare subscribe: no pacing, no count)
"""
import asyncio, json, time
import websockets

async def main():
    uri = "ws://127.0.0.1:8000/ws/events?session=probe_s55"
    times, msgs = [], []
    async with websockets.connect(uri) as ws:
        while True:
            m = await ws.recv()
            times.append(time.perf_counter()); msgs.append(m)
            if json.loads(m).get("type") == "end":
                break
    gaps = [round((b - a) * 1000) for a, b in zip(times, times[1:])]
    print("messages", len(msgs), "gaps_ms", gaps)
    assert len(msgs) >= 3, "expected events + end"
    assert all(g >= 30 for g in gaps[:-1]), f"burst detected {gaps}"
    print("PACING_OK bare subscribe paced ~50ms")

asyncio.run(main())
