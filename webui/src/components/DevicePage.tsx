import { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import TimeSeries from "./Charts/TimeSeries";
import Histogram from "./Charts/Histogram";
import Sparkline from "./Charts/Sparkline";
import { useAppStore } from "../store/useAppStore";

const TABS = ["overview", "imu", "loop", "power", "raw"] as const;

const PROFILE_LIMITS = {
  usb_stand: {
    max_tilt: 25,
    max_gyro_std: 6,
    max_gyro_bias: 12,
    max_cyc_jitter: 20,
    max_accnorm_std: 6,
    min_vbat: 0,
    max_amps: 0.5,
  },
  field_strict: {
    max_tilt: 12,
    max_gyro_std: 4,
    max_gyro_bias: 8,
    max_cyc_jitter: 10,
    max_accnorm_std: 4,
    min_vbat: 4,
    max_amps: 0.35,
  },
};

export default function DevicePage() {
  const { uid } = useParams<{ uid: string }>();
  const [tab, setTab] = useState<(typeof TABS)[number]>("overview");
  const devices = useAppStore((state) => state.devices);
  const profile = useAppStore((state) => state.profile);
  const device = uid ? devices[uid] : undefined;

  if (!device) {
    return (
      <div className="p-8 space-y-4">
        <Link to="/" className="btn-outline w-fit">← Back</Link>
        <div className="text-muted">Device not found</div>
      </div>
    );
  }

  const history = device.history ?? { cycle_us: [], loop_hz: [], vbat: [], amps: [] };
  const loop = device.loop ?? {};
  const imu = device.imu_stats ?? {};
  const analog = device.analog ?? {};
  const attitude = device.attitude ?? {};
  const limits = PROFILE_LIMITS[profile as keyof typeof PROFILE_LIMITS] ?? PROFILE_LIMITS.usb_stand;
  const rawPackets = (device.raw_packets ?? []) as Array<{ ts: number; cmd: number; len: number; payload_hex: string }>;
  const [cmdFilter, setCmdFilter] = useState<string>("");

  const filteredPackets = useMemo(() => {
    if (!cmdFilter) return rawPackets.slice(-200).reverse();
    const cmd = parseInt(cmdFilter, 10);
    if (Number.isNaN(cmd)) return rawPackets.slice(-200).reverse();
    return rawPackets.filter((packet) => packet.cmd === cmd).slice(-200).reverse();
  }, [cmdFilter, rawPackets]);

  return (
    <div className="space-y-6 p-6 pb-24">
      <Link to="/" className="btn-outline w-fit">← Back</Link>
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div className="space-y-1">
          <h1 className="text-3xl font-semibold">{device.uid ?? device.port}</h1>
          <div className="text-muted">Port {device.port}</div>
          <div className="text-xs text-muted">Updated {device.updated ? new Date(device.updated * 1000).toLocaleTimeString() : "—"}</div>
        </div>
        <div className="flex gap-2">
          {TABS.map((item) => (
            <button
              key={item}
              className={`chip ${tab === item ? "chip-active" : ""}`}
              onClick={() => setTab(item)}
            >
              {item.toUpperCase()}
            </button>
          ))}
        </div>
      </header>

      {tab === "overview" && (
        <section className="space-y-4">
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <MetricCard title="Loop Hz" value={`${(loop.loop_hz ?? 0).toFixed(1)}`} subtitle={`${(loop.mean_us ?? 0).toFixed(1)} µs`} />
            <MetricCard title="Jitter" value={`${(loop.std_us ?? 0).toFixed(2)} µs`} subtitle={`limit ${limits.max_cyc_jitter} µs`} />
            <MetricCard title="VBAT" value={`${(analog.vbat_V ?? 0).toFixed(2)} V`} subtitle={`≥ ${limits.min_vbat} V`} />
            <MetricCard title="Current" value={`${(analog.amps_A ?? 0).toFixed(2)} A`} subtitle={`≤ ${limits.max_amps} A`} />
          </div>
          <div className="card">
            <h2 className="text-lg font-semibold mb-4">Attitude & thresholds</h2>
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 text-sm text-muted">
              <div>
                <div className="text-xs uppercase">Roll</div>
                <div className="text-lg font-semibold">{(attitude.roll_deg ?? 0).toFixed(1)}°</div>
              </div>
              <div>
                <div className="text-xs uppercase">Pitch</div>
                <div className="text-lg font-semibold">{(attitude.pitch_deg ?? 0).toFixed(1)}°</div>
              </div>
              <div>
                <div className="text-xs uppercase">Tilt limit</div>
                <div className="text-lg font-semibold">{limits.max_tilt}°</div>
              </div>
              <div>
                <div className="text-xs uppercase">I²C errors/s</div>
                <div className="text-lg font-semibold">{(device.status?.i2c_errors ?? 0)}</div>
              </div>
            </div>
          </div>
          <div className="card">
            <h2 className="text-lg font-semibold mb-4">Loop trend</h2>
            <Sparkline data={history.loop_hz.slice(-120)} color="#38bdf8" />
          </div>
        </section>
      )}

      {tab === "imu" && (
        <section className="space-y-4">
          <div className="card space-y-4">
            <h2 className="text-lg font-semibold">Gyro statistics</h2>
            <div className="grid grid-cols-3 gap-3 text-sm">
              {(imu.gyro_std ?? []).map((value: number, idx: number) => (
                <MetricCard key={idx} title={`σ axis ${"XYZ"[idx]}`} value={`${value.toFixed(2)} dps`} subtitle={`limit ${limits.max_gyro_std}`} />
              ))}
            </div>
            <div className="grid grid-cols-3 gap-3 text-sm text-muted">
              {(imu.gyro_bias ?? []).map((value: number, idx: number) => (
                <div key={`bias-${idx}`}>
                  <div className="text-xs uppercase tracking-wide">Bias {"XYZ"[idx]}</div>
                  <div className="text-lg font-semibold">{value.toFixed(2)} dps</div>
                  <div className="text-xs text-muted">limit ±{limits.max_gyro_bias}</div>
                </div>
              ))}
            </div>
          </div>
          <div className="card space-y-4">
            <h2 className="text-lg font-semibold">Acceleration norm</h2>
            <div className="text-sm text-muted">σ = {(imu.acc_norm_std ?? 0).toFixed(2)} (limit {limits.max_accnorm_std})</div>
          </div>
        </section>
      )}

      {tab === "loop" && (
        <section className="space-y-4">
          <div className="card space-y-4">
            <h2 className="text-lg font-semibold">Cycle time</h2>
            <TimeSeries title="Cycle µs" data={history.cycle_us.slice(-180)} />
            <Histogram title="Jitter histogram" data={history.cycle_us.slice(-180)} />
          </div>
        </section>
      )}

      {tab === "power" && (
        <section className="space-y-4">
          <div className="card space-y-4">
            <h2 className="text-lg font-semibold">Power trends</h2>
            <TimeSeries title="VBAT" data={history.vbat.slice(-180)} color="#facc15" />
            <TimeSeries title="Current" data={history.amps.slice(-180)} color="#fb7185" />
          </div>
          <div className="card space-y-3">
            <h2 className="text-lg font-semibold">Meters</h2>
            <table className="w-full text-sm">
              <thead className="text-muted">
                <tr className="text-left">
                  <th>ID</th>
                  <th>Type</th>
                  <th>Raw</th>
                  <th>Value</th>
                </tr>
              </thead>
              <tbody>
                {(device.voltage_meters?.meters ?? []).map((meter: any) => (
                  <tr key={`voltage-${meter.id}`} className="border-t border-border/40">
                    <td>{meter.id}</td>
                    <td>Voltage</td>
                    <td>{meter.value_raw}</td>
                    <td>{(meter.voltage_V ?? 0).toFixed(2)} V</td>
                  </tr>
                ))}
                {(device.current_meters?.meters ?? []).map((meter: any) => (
                  <tr key={`current-${meter.id}`} className="border-t border-border/40">
                    <td>{meter.id}</td>
                    <td>Current</td>
                    <td>{meter.value_raw}</td>
                    <td>{(meter.amps_A ?? 0).toFixed(2)} A</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {tab === "raw" && (
        <section className="card space-y-4">
          <div className="flex items-center gap-3">
            <h2 className="text-lg font-semibold">Raw MSP packets</h2>
            <input
              className="input w-32"
              placeholder="CMD"
              value={cmdFilter}
              onChange={(e) => setCmdFilter(e.target.value)}
            />
          </div>
          <div className="overflow-auto max-h-[420px] text-xs">
            <table className="w-full">
              <thead className="text-muted sticky top-0 bg-surface">
                <tr className="text-left">
                  <th className="px-2 py-1">Time</th>
                  <th className="px-2 py-1">CMD</th>
                  <th className="px-2 py-1">Len</th>
                  <th className="px-2 py-1">Payload</th>
                </tr>
              </thead>
              <tbody>
                {filteredPackets.map((pkt) => (
                  <tr key={`${pkt.ts}-${pkt.cmd}-${pkt.len}`} className="border-t border-border/40">
                    <td className="px-2 py-1">{new Date(pkt.ts * 1000).toLocaleTimeString()}</td>
                    <td className="px-2 py-1">{pkt.cmd}</td>
                    <td className="px-2 py-1">{pkt.len}</td>
                    <td className="px-2 py-1 font-mono text-xs break-all">{pkt.payload_hex}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </div>
  );
}

function MetricCard({ title, value, subtitle }: { title: string; value: string; subtitle?: string }) {
  return (
    <div className="card space-y-1">
      <div className="text-xs uppercase tracking-wide text-muted">{title}</div>
      <div className="text-2xl font-semibold">{value}</div>
      {subtitle && <div className="text-xs text-muted">{subtitle}</div>}
    </div>
  );
}
