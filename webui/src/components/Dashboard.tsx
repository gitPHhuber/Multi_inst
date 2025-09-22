import { useEffect } from "react";
import { useAppStore, useFilteredDevices } from "../store/useAppStore";
import DeviceCard from "./DeviceCard";

const STATUS_FILTERS = [
  { key: "all", label: "All" },
  { key: "ok", label: "OK" },
  { key: "not_ok", label: "NOT OK" },
  { key: "testing", label: "Testing" },
] as const;

export default function Dashboard() {
  const devices = useFilteredDevices();
  const {
    sessionId,
    loading,
    error,
    mode,
    auto,
    profile,
    fps,
    start,
    stop,
    refreshPorts,
    ports,
    toggleTheme,
    theme,
    filter,
    search,
    sort,
    setFilter,
    setSearch,
    setSort,
    setMode,
    setAuto,
    setProfile,
    setSimulate,
    setIncludeSimulator,
    simulate,
    includeSimulator,
  } = useAppStore((state) => ({
    sessionId: state.sessionId,
    loading: state.loading,
    error: state.error,
    mode: state.mode,
    auto: state.auto,
    profile: state.profile,
    fps: state.fps,
    start: state.start,
    stop: state.stop,
    refreshPorts: state.refreshPorts,
    ports: state.ports,
    toggleTheme: state.toggleTheme,
    theme: state.theme,
    filter: state.filter,
    search: state.search,
    sort: state.sort,
    setFilter: state.setFilter,
    setSearch: state.setSearch,
    setSort: state.setSort,
    setMode: state.setMode,
    setAuto: state.setAuto,
    setProfile: state.setProfile,
    setSimulate: state.setSimulate,
    setIncludeSimulator: state.setIncludeSimulator,
    simulate: state.simulate,
    includeSimulator: state.includeSimulator,
  }));

  useEffect(() => {
    refreshPorts();
  }, [refreshPorts]);

  const totals = summarize(devices);

  return (
    <div className="space-y-6 pb-24">
      <header className="sticky top-0 z-10 backdrop-blur bg-surface/75 border-b border-border">
        <div className="flex flex-wrap items-center justify-between gap-4 px-6 py-4">
          <div>
            <h1 className="text-2xl font-semibold">Multi Inst Diagnostics</h1>
            <p className="text-sm text-muted">Auto-flow diagnostics for Betaflight flight controllers.</p>
          </div>
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <button
              className="btn-secondary"
              disabled={loading}
              onClick={() => refreshPorts()}
            >
              Scan
            </button>
            {sessionId ? (
              <button className="btn-outline" onClick={() => stop()} disabled={loading}>
                Stop
              </button>
            ) : (
              <button className="btn-primary" onClick={() => start()} disabled={loading}>
                Start
              </button>
            )}
            <div className="divider" />
            <label className="control">
              <span>Mode</span>
              <select
                value={mode}
                onChange={(e) => setMode(e.target.value as "normal" | "pro")}
              >
                <option value="normal">Normal</option>
                <option value="pro">Pro</option>
              </select>
            </label>
            <label className="control">
              <span>Auto</span>
              <input
                type="checkbox"
                checked={auto}
                onChange={(e) => setAuto(e.target.checked)}
              />
            </label>
            <label className="control">
              <span>Profile</span>
              <select
                value={profile}
                onChange={(e) =>
                  setProfile(e.target.value as "usb_stand" | "field_strict")
                }
              >
                <option value="usb_stand">USB Stand</option>
                <option value="field_strict">Field Strict</option>
              </select>
            </label>
            <label className="control">
              <span>Sim</span>
              <input
                type="checkbox"
                checked={simulate}
                onChange={(e) => setSimulate(e.target.checked)}
              />
            </label>
            <label className="control">
              <span>Include sim://</span>
              <input
                type="checkbox"
                checked={includeSimulator}
                onChange={(e) => setIncludeSimulator(e.target.checked)}
              />
            </label>
            <button className="btn-ghost" onClick={toggleTheme}>
              {theme === "dark" ? "🌙" : "☀️"}
            </button>
            <div className="text-xs text-muted">
              Devices {devices.length} · FPS {fps}
            </div>
          </div>
        </div>
        {error && (
          <div className="px-6 pb-4 text-sm text-rose-400">{error}</div>
        )}
      </header>

      <section className="px-6 space-y-4">
        <div className="flex flex-wrap items-center gap-3">
          {STATUS_FILTERS.map((item) => (
            <button
              key={item.key}
              className={`chip ${filter === item.key ? "chip-active" : ""}`}
              onClick={() => setFilter(item.key)}
            >
              {item.label}
            </button>
          ))}
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search UID or port..."
            className="input flex-1 min-w-[200px]"
          />
          <select
            value={sort}
            onChange={(e) => setSort(e.target.value as any)}
            className="input w-40"
          >
            <option value="status">Sort by status</option>
            <option value="port">Sort by port</option>
            <option value="updated">Sort by time</option>
          </select>
        </div>

        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {devices.map((device) => (
            <DeviceCard
              key={device.uid ?? device.port}
              device={device}
              mode={mode}
              profile={profile}
            />
          ))}
          {!devices.length && (
            <div className="card-muted text-center py-16 text-muted">
              No devices detected. Connect a flight controller and press Start.
            </div>
          )}
        </div>
      </section>

      <footer className="fixed bottom-0 left-0 right-0 bg-surface/90 backdrop-blur border-t border-border px-6 py-4">
        <div className="flex flex-wrap items-center justify-between gap-3 text-sm">
          <div className="font-semibold">Summary</div>
          <div className="flex flex-wrap gap-4 text-muted">
            <span>Total {totals.total}</span>
            <span>OK {totals.ok}</span>
            <span>NOT OK {totals.notOk}</span>
            <span>Testing {totals.testing}</span>
            {totals.reasons.map((reason) => (
              <span key={reason.id} className="chip chip-muted">
                {reason.id} · {reason.count}
              </span>
            ))}
          </div>
          <div className="text-xs text-muted">
            Available ports: {ports.map((p) => p.device).join(", ") || "—"}
          </div>
        </div>
      </footer>
    </div>
  );
}

function summarize(devices: ReturnType<typeof useFilteredDevices>) {
  const totals = {
    total: devices.length,
    ok: 0,
    notOk: 0,
    testing: 0,
    reasons: new Map<string, number>(),
  };
  devices.forEach((device) => {
    if (device.state === "testing") totals.testing += 1;
    if (device.ok === true) totals.ok += 1;
    if (device.ok === false) totals.notOk += 1;
    device.reasons?.forEach((reason) => {
      const key = reason.split(" ")[0];
      totals.reasons.set(key, (totals.reasons.get(key) ?? 0) + 1);
    });
  });
  return {
    total: totals.total,
    ok: totals.ok,
    notOk: totals.notOk,
    testing: totals.testing,
    reasons: Array.from(totals.reasons, ([id, count]) => ({ id, count })),
  };
}
