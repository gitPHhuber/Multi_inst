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

CLI режим поддерживает автоматический поток тестирования, выбор профиля и режим отображения:

```bash
multi-inst \
  --out ./out \
  --profile usb_stand \
  --mode pro \
  --auto \
  --duration 6 \
  --include-sim \
  --simulate
```

Доступны флаги `--disable-whitelist` (для отключения фильтрации VID/PID), `--no-auto` (ручной запуск), `--mode normal|pro`, `--profile usb_stand|field_strict`.

### Web UI

```bash
cd webui
npm install
npm run dev
```

Откройте http://localhost:5173 для отображения дашборда. Интерфейс использует WebSocket-поток, поэтому агент должен быть запущен.

## Возможности

- **Сканер портов:** фильтрует только USB-VCP (`/dev/ttyACM*`, `/dev/ttyUSB*`) и проверяет доступность контроллера MSP-пингом (MSP_API_VERSION).
- **Авто-поток:** вставка устройства инициирует тест (≥10 Гц MSP-опрос, фиксация JSON-отчётов). При отключённом авто-режиме тесты можно запускать кнопкой *Retest*.
- **Профили порогов:** `usb_stand` и `field_strict` управляют расчётом OK/NOT OK (жёсткие лимиты на джиттер, ток, наклон, шум IMU).
- **Режимы отображения:**
  - *Normal* — крупный статус, причины отказа, базовые метрики (Loop Hz, VBAT, ток).
  - *Pro* — UID/вариант, мини-графики (loop, VBAT, ток), бейджи ошибок.
- **Детальный просмотр устройства:** вкладки Overview/IMU/Loop/Power/Raw с живыми графиками, таблицами и фильтром по MSP-командам.
- **Тёмная/светлая тема, sticky-summary и фильтры (статус, поиск, сортировка).**

## Скриншоты

![Dashboard](docs/dashboard.png)

![Device details](docs/device-details.png)
