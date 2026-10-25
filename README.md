# PKS Sensor Network (UDP + JSON)

A UDP server and sensor simulator for an IoT weather-station protocol, written in
plain Python (standard library only). Course project for Computer Networks (PKS)
at FIIT STU.

## What it does

- Sensors **register** with the server and receive a session token.
- The server accepts periodic **DATA** messages from many sensors of four types
  (`ThermoNode`, `WindSense`, `RainDetect`, `AirQuality`).
- Every message carries a **CRC32**; corrupted payloads trigger
  `RETRANSMIT_REQUEST` and the original frame is resent.
- Reliable delivery uses **ACK** messages and a pending-message queue.
- Keep-alive handling detects sensors that stop sending.
- The server logs every event (UTC timestamps) to `server.log`.
- `tester.py` is a menu-driven simulator: register sensors, send custom values,
  corrupt the next frame, disconnect a sensor, or run automatic sending.

## Tech stack

- Python 3 (stdlib: `socket`, `threading`, `json`, `zlib`, `secrets`, `datetime`)
- UDP on port **5055** by default
- Custom JSON message envelope with sequence numbers and CRC32

## Architecture

```
client/sensor (tester.py)  <--UDP/JSON-->  server.py
        |                                      |
   pending queue                         sensor registry
   ACK / retransmit                      CRC validation
   auto-send thread                      keep-alive tracking
```

Both programs expose an interactive console menu, so the protocol can be exercised
without extra tooling.

## How to run

```bash
# terminal 1
python server.py

# terminal 2
python tester.py
```

Use `127.0.0.1` and port `5055` for a local run; the tester can also point at
another machine on the LAN.

## Documentation

- `docs/PKS_dokumentacia.pdf` - protocol and implementation write-up
- `docs/protocol.html` - generated protocol documentation
- `docs/diagramy/` - SVG flow, sequence and chart diagrams used by the HTML page
- `docs/make_diagrams.py` - script that regenerates the diagrams

## What I learned

- Designing a small application-level protocol on top of UDP.
- Handling loss/corruption with CRC32, ACKs and retransmission.
- Concurrency in Python: one receive loop, per-sensor state, and background senders.
- Writing a simulator that makes protocol behaviour reproducible.

## Author

Ondrej Nebus — FIIT STU, 2025/26.
