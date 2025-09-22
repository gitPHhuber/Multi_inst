import create from "zustand";
import {
  DeviceSnapshot,
  StartOptions,
  fetchPorts,
  openStream,
  retestDevice,
  startSession,
  stopSession,
} from "../lib/api";

type DeviceMap = Record<string, DeviceSnapshot>;

type FilterType = "all" | "ok" | "not_ok" | "testing";
type SortType = "status" | "port" | "updated";

interface AppState {
  sessionId: string | null;
  devices: DeviceMap;
  loading: boolean;
  error: string | null;
  mode: "normal" | "pro";
  auto: boolean;
  profile: "usb_stand" | "field_strict";
  simulate: boolean;
  includeSimulator: boolean;
  filter: FilterType;
  search: string;
  sort: SortType;
  fps: number;
  frames: number;
  lastFrameTs: number;
  theme: "dark" | "light";
  ports: Array<Record<string, any>>;
  start: (options?: Partial<StartOptions>) => Promise<void>;
  stop: () => Promise<void>;
  refreshPorts: () => Promise<void>;
  setMode: (mode: "normal" | "pro") => Promise<void>;
  setAuto: (auto: boolean) => Promise<void>;
  setProfile: (profile: "usb_stand" | "field_strict") => Promise<void>;
  setSimulate: (simulate: boolean) => Promise<void>;
  setIncludeSimulator: (value: boolean) => Promise<void>;
  setFilter: (filter: FilterType) => void;
  setSearch: (search: string) => void;
  setSort: (sort: SortType) => void;
  toggleTheme: () => void;
  retest: (uid: string) => Promise<void>;
  handleEvent: (event: any) => void;
}

let ws: WebSocket | null = null;

function closeWebSocket() {
  if (ws) {
    ws.close();
    ws = null;
  }
}

export const useAppStore = create<AppState>((set, get) => ({
  sessionId: null,
  devices: {},
  loading: false,
  error: null,
  mode: "normal",
  auto: true,
  profile: "usb_stand",
  simulate: false,
  includeSimulator: false,
  filter: "all",
  search: "",
  sort: "status",
  fps: 0,
  frames: 0,
  lastFrameTs: 0,
  theme: "dark",
  ports: [],
  start: async (options) => {
    const state = get();
    if (state.loading) return;
    set({ loading: true, error: null, devices: {}, fps: 0, frames: 0, lastFrameTs: 0 });
    try {
      const sessionId = await startSession({
        simulate: options?.simulate ?? state.simulate,
        ports: options?.ports ?? [],
        profile: options?.profile ?? state.profile,
        mode: options?.mode ?? state.mode,
        auto: options?.auto ?? state.auto,
        enforceWhitelist: options?.enforceWhitelist ?? true,
        includeSimulator: options?.includeSimulator ?? state.includeSimulator,
        duration: options?.duration ?? 5,
      });
      set({ sessionId, devices: {} });
      closeWebSocket();
      ws = openStream(sessionId);
      ws.onmessage = (msg) => {
        try {
          const payload = JSON.parse(msg.data);
          get().handleEvent(payload);
        } catch (err) {
          console.warn("Failed to parse message", err);
        }
      };
      ws.onclose = () => {
        if (get().sessionId === sessionId) {
          set({ sessionId: null });
        }
      };
    } catch (err: any) {
      set({ error: String(err) });
    } finally {
      set({ loading: false });
    }
  },
  stop: async () => {
    const sessionId = get().sessionId;
    if (!sessionId) return;
    await stopSession(sessionId);
    closeWebSocket();
    set({ sessionId: null, devices: {}, fps: 0, frames: 0, lastFrameTs: 0 });
  },
  refreshPorts: async () => {
    const ports = await fetchPorts();
    set({ ports });
  },
  setMode: async (mode) => {
    set({ mode });
    if (get().sessionId) {
      await get().stop();
      await get().start();
    }
  },
  setAuto: async (auto) => {
    set({ auto });
    if (get().sessionId) {
      await get().stop();
      await get().start();
    }
  },
  setProfile: async (profile) => {
    set({ profile });
    if (get().sessionId) {
      await get().stop();
      await get().start();
    }
  },
  setSimulate: async (simulate) => {
    set({ simulate });
    if (get().sessionId) {
      await get().stop();
      await get().start();
    }
  },
  setIncludeSimulator: async (value) => {
    set({ includeSimulator: value });
    if (get().sessionId) {
      await get().stop();
      await get().start();
    }
  },
  setFilter: (filter) => set({ filter }),
  setSearch: (search) => set({ search }),
  setSort: (sort) => set({ sort }),
  toggleTheme: () => {
    const next = get().theme === "dark" ? "light" : "dark";
    set({ theme: next });
    document.documentElement.dataset.theme = next;
  },
  retest: async (uid: string) => {
    const sessionId = get().sessionId;
    if (!sessionId) return;
    await retestDevice(sessionId, uid);
  },
  handleEvent: (event: any) => {
    const { devices, frames, lastFrameTs } = get();
    if (event.type === "snapshot") {
      const uid = event.uid as string;
      const nextDevices: DeviceMap = { ...devices, [uid]: event.data };
      let newFrames = frames + 1;
      let lastTs = lastFrameTs || Date.now();
      let fps = get().fps;
      const now = Date.now();
      if (now - lastTs >= 1000) {
        fps = Math.round((newFrames * 1000) / (now - lastTs));
        newFrames = 0;
        lastTs = now;
      }
      set({ devices: nextDevices, frames: newFrames, lastFrameTs: lastTs, fps });
    } else if (event.type === "removed") {
      const nextDevices: DeviceMap = { ...devices };
      delete nextDevices[event.uid as string];
      set({ devices: nextDevices });
    } else if (event.type === "probe_failed") {
      set({ error: event.reason });
    }
  },
}));

export function useFilteredDevices(): DeviceSnapshot[] {
  const { devices, filter, search, sort } = useAppStore((state) => ({
    devices: state.devices,
    filter: state.filter,
    search: state.search,
    sort: state.sort,
  }));
  const entries = Object.values(devices);
  const normalizedSearch = search.trim().toLowerCase();
  const filtered = entries.filter((device) => {
    if (!normalizedSearch) {
      return filterDevice(device, filter);
    }
    const label = `${device.uid ?? ""} ${device.port}`.toLowerCase();
    return label.includes(normalizedSearch) && filterDevice(device, filter);
  });
  return filtered.sort((a, b) => compareDevices(a, b, sort));
}

function filterDevice(device: DeviceSnapshot, filter: FilterType): boolean {
  if (filter === "all") return true;
  if (filter === "testing") return device.state === "testing";
  if (filter === "ok") return device.ok === true;
  if (filter === "not_ok") return device.ok === false;
  return true;
}

function compareDevices(a: DeviceSnapshot, b: DeviceSnapshot, sort: SortType): number {
  if (sort === "port") {
    return (a.port ?? "").localeCompare(b.port ?? "");
  }
  if (sort === "updated") {
    return (b.updated ?? 0) - (a.updated ?? 0);
  }
  // sort by status severity
  const order = (device: DeviceSnapshot) => {
    if (device.state === "testing") return 0;
    if (device.ok === false) return 1;
    if (device.ok === true) return 2;
    return 3;
  };
  return order(a) - order(b);
}
