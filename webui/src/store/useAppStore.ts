import create from "zustand";
import { fetchSnapshot, startSession, stopSession } from "../lib/api";

interface AppState {
  sessionId: string | null;
  devices: any[];
  loading: boolean;
  error: string | null;
  start: () => Promise<void>;
  refresh: () => Promise<void>;
  stop: () => Promise<void>;
}

export const useAppStore = create<AppState>((set, get) => ({
  sessionId: null,
  devices: [],
  loading: false,
  error: null,
  start: async () => {
    set({ loading: true, error: null });
    try {
      const sessionId = await startSession(true);
      set({ sessionId });
      await get().refresh();
    } catch (err) {
      set({ error: String(err) });
    } finally {
      set({ loading: false });
    }
  },
  refresh: async () => {
    const sessionId = get().sessionId;
    if (!sessionId) return;
    const data = await fetchSnapshot(sessionId);
    set({ devices: data.devices });
  },
  stop: async () => {
    const sessionId = get().sessionId;
    if (!sessionId) return;
    await stopSession(sessionId);
    set({ sessionId: null, devices: [] });
  }
}));
