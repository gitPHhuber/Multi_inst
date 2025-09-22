import axios from "axios";

const API_BASE = "http://127.0.0.1:8765";

export interface DeviceSnapshot {
  uid?: string;
  port: string;
  ok: boolean | null;
  reasons: string[];
  state: string;
  profile: string;
  mode: string;
  meta?: Record<string, any>;
  status?: Record<string, any>;
  attitude?: Record<string, any>;
  analog?: Record<string, any>;
  loop?: Record<string, any>;
  imu_stats?: Record<string, any>;
  voltage_meters?: Record<string, any>;
  current_meters?: Record<string, any>;
  history?: {
    cycle_us: number[];
    loop_hz: number[];
    vbat: number[];
    amps: number[];
  };
  raw_packets?: Array<{ ts: number; cmd: number; len: number; payload_hex: string }>;
  updated?: number;
  duration_s?: number;
}

export async function fetchSnapshot(sessionId: string) {
  const res = await axios.get(`${API_BASE}/v1/snapshot`, {
    params: { session_id: sessionId },
  });
  return res.data as { session_id: string; devices: DeviceSnapshot[] };
}

export interface StartOptions {
  simulate?: boolean;
  ports?: string[];
  profile?: string;
  mode?: "normal" | "pro";
  auto?: boolean;
  enforceWhitelist?: boolean;
  includeSimulator?: boolean;
  duration?: number;
}

export async function startSession(options: StartOptions) {
  const res = await axios.post(`${API_BASE}/v1/start`, {
    ports: options.ports ?? [],
    simulate: options.simulate ?? false,
    profile: options.profile ?? "usb_stand",
    mode: options.mode ?? "normal",
    auto: options.auto ?? true,
    enforce_whitelist: options.enforceWhitelist ?? true,
    include_simulator: options.includeSimulator ?? false,
    duration: options.duration ?? 5,
  });
  return res.data.session_id as string;
}

export async function stopSession(sessionId: string) {
  await axios.post(`${API_BASE}/v1/stop`, { session_id: sessionId });
}

export async function retestDevice(sessionId: string, uid: string) {
  await axios.post(`${API_BASE}/v1/retest`, undefined, {
    params: { session_id: sessionId, uid },
  });
}

export async function fetchPorts() {
  const res = await axios.get(`${API_BASE}/v1/ports`);
  return res.data.ports as Array<Record<string, any>>;
}

export function openStream(sessionId: string): WebSocket {
  const ws = new WebSocket(`ws://127.0.0.1:8765/v1/stream?session_id=${sessionId}`);
  return ws;
}
