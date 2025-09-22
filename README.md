# Multi Inst Diagnostic Suite

Монорепозиторий производственного инструмента диагностики полётных контроллеров Betaflight.

## Структура

- `agent/` — локальный агент (FastAPI, CLI).
- `webui/` — веб-интерфейс (React + Vite + Tailwind + ECharts).

## Быстрый старт

### Agent

```bash
cd agent
python3 -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
uvicorn multi_inst_agent.api.app:app --host 127.0.0.1 --port 8765
```

CLI режим:

```bash
multi-inst --out ./out --workers 6 --simulate
```

### Web UI

```bash
cd webui
npm install
npm run dev
```

Откройте http://localhost:5173 для отображения дашборда.
