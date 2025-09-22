import axios from "axios";

const API_BASE = "http://127.0.0.1:8765";

export interface DeviceSnapshot {
  uid: string;
  port: string;
  ok: boolean;
  reasons: string[];
  loop_stats?: {
    cycle_us_mean: number;
    cycle_us_std: number;
    loop_hz_mean: number;
  };
  analog?: {
    vbat_V: number;
    amps_A: number;
  };
}

export async function fetchSnapshot(sessionId: string) {
  const res = await axios.get(`${API_BASE}/v1/snapshot`, { params: { session_id: sessionId } });
  return res.data;
}

export async function startSession(sim: boolean = true) {
  const res = await axios.post(`${API_BASE}/v1/start`, { ports: [], simulate: sim });
  return res.data.session_id as string;
}

export async function stopSession(sessionId: string) {
  await axios.post(`${API_BASE}/v1/stop`, { session_id: sessionId });
}
