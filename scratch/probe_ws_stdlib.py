"""Bare WS subscribe pacing via stdlib socket (no websockets dep)."""
import base64, hashlib, json, os, socket, struct, time

s = socket.create_connection(("127.0.0.1", 8000), timeout=5)
key = base64.b64encode(os.urandom(16)).decode()
req = (f"GET /ws/events?session=probe_s55 HTTP/1.1\r\nHost: 127.0.0.1:8000\r\n"
       f"Upgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n")
s.sendall(req.encode())
buf = b""
while b"\r\n\r\n" not in buf:
    buf += s.recv(4096)
head, buf = buf.split(b"\r\n\r\n", 1)
print(head.decode(errors="replace").splitlines()[0])
assert b"101" in head.split(b"\r\n")[0]

def read_exact(n):
    global buf
    while len(buf) < n:
        buf += s.recv(4096)
    out, buf = buf[:n], buf[n:]
    return out

times, msgs = [], []
while True:
    h = read_exact(2); opcode = h[0] & 15; ln = h[1] & 127
    if ln == 126: ln = struct.unpack(">H", read_exact(2))[0]
    elif ln == 127: ln = struct.unpack(">Q", read_exact(8))[0]
    payload = read_exact(ln) if ln else b""
    if opcode == 8: break
    if opcode in (1, 2):
        times.append(time.perf_counter()); msgs.append(payload.decode())
        if json.loads(payload).get("type") == "end": break
gaps = [round((b - a) * 1000) for a, b in zip(times, times[1:])]
print("messages", len(msgs), "gaps_ms", gaps)
assert len(msgs) == 6 and all(g >= 30 for g in gaps[:-1]), gaps
print("PACING_OK bare subscribe paced ~50ms")
