# Multi Inst Agent

FastAPI based agent that polls Betaflight flight controllers and exposes results via HTTP/WebSocket.

## Development

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
uvicorn multi_inst_agent.api.app:app --host 127.0.0.1 --port 8765
```
