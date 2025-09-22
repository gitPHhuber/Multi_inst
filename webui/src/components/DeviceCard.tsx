import { Link } from "react-router-dom";
import { DeviceSnapshot } from "../lib/api";
import { useAppStore } from "../store/useAppStore";
import Sparkline from "./Charts/Sparkline";

type Props = {
  device: DeviceSnapshot;
  mode: "normal" | "pro";
  profile: string;
};

const STATUS_CLASS = {
  ok: "bg-emerald-500/20 text-emerald-300 border border-emerald-500/40",
  fail: "bg-rose-500/20 text-rose-300 border border-rose-500/40",
  testing: "bg-amber-500/15 text-amber-300 border border-amber-400/40",
};

export default function DeviceCard({ device, mode, profile }: Props) {
  const retest = useAppStore((state) => state.retest);
  const status = deriveStatus(device);
  const loopHz = device.loop?.loop_hz ?? 0;
  const cycleUs = device.loop?.mean_us ?? 0;
  const jitter = device.loop?.std_us ?? 0;
  const vbat = device.analog?.vbat_V ?? 0;
  const amps = device.analog?.amps_A ?? 0;
  const reasons = device.reasons ?? [];
  const history = device.history ?? { cycle_us: [], loop_hz: [], vbat: [], amps: [] };
  const meta = device.meta ?? {};

  return (
    <div className="card space-y-4">
      <header className="flex items-start justify-between gap-4">
        <div className="space-y-1">
          <div className="text-sm text-muted">{device.port}</div>
          <div className="text-xl font-semibold">{device.uid ?? "Unknown"}</div>
          <div className="text-xs text-muted">Profile · {profile}</div>
        </div>
        <div className={`px-3 py-1 rounded-full text-xs font-semibold ${STATUS_CLASS[status]}`}>
          {statusLabel(status)}
        </div>
      </header>

      {mode === "normal" ? (
        <NormalCard
          device={device}
          loopHz={loopHz}
          cycleUs={cycleUs}
          jitter={jitter}
          vbat={vbat}
          amps={amps}
          reasons={reasons}
          history={history}
          onRetest={() => retest(device.uid ?? "")}
        />
      ) : (
        <ProCard
          device={device}
          loopHz={loopHz}
          cycleUs={cycleUs}
          jitter={jitter}
          vbat={vbat}
          amps={amps}
          history={history}
          reasons={reasons}
          meta={meta}
          onRetest={() => retest(device.uid ?? "")}
        />
      )}
    </div>
  );
}

type NormalProps = {
  device: DeviceSnapshot;
  loopHz: number;
  cycleUs: number;
  jitter: number;
  vbat: number;
  amps: number;
  reasons: string[];
  history: NonNullable<DeviceSnapshot["history"]>;
  onRetest: () => void;
};

function NormalCard({ device, loopHz, cycleUs, jitter, vbat, amps, reasons, history, onRetest }: NormalProps) {
  const shortReasons = reasons.slice(0, 6);
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-3 gap-3 text-center text-sm">
        <Stat label="Loop Hz" value={`${loopHz.toFixed(1)}`} />
        <Stat label="Cycle µs" value={`${cycleUs.toFixed(1)}`} sub={`±${jitter.toFixed(1)}`} />
        <Stat label="VBAT" value={`${vbat.toFixed(1)} V`} sub={`${amps.toFixed(2)} A`} />
      </div>
      <div className="flex flex-wrap gap-2">
        {shortReasons.length ? (
          shortReasons.map((reason) => (
            <span key={reason} className="chip chip-muted text-xs">
              {formatReason(reason)}
            </span>
          ))
        ) : (
          <span className="text-xs text-muted">No issues detected</span>
        )}
      </div>
      <Sparkline data={history.loop_hz.slice(-40)} color="#38bdf8" />
      <div className="flex justify-between gap-2 text-sm">
        <button className="btn-secondary flex-1" onClick={(e) => { e.preventDefault(); onRetest(); }}>
          Retest
        </button>
        <Link className="btn-outline flex-1 text-center" to={`/device/${device.uid ?? device.port}`}>
          Details
        </Link>
      </div>
    </div>
  );
}

type ProProps = {
  device: DeviceSnapshot;
  loopHz: number;
  cycleUs: number;
  jitter: number;
  vbat: number;
  amps: number;
  history: NonNullable<DeviceSnapshot["history"]>;
  reasons: string[];
  meta: Record<string, any>;
  onRetest: () => void;
};

function ProCard({ device, loopHz, cycleUs, jitter, vbat, amps, history, reasons, meta, onRetest }: ProProps) {
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 text-sm text-muted">
        <div>
          <span className="text-xs uppercase tracking-wide text-muted">UID</span>
          <div>{device.uid ?? "—"}</div>
        </div>
        <div>
          <span className="text-xs uppercase tracking-wide text-muted">Variant</span>
          <div>{meta.fc_variant ?? "—"}</div>
        </div>
        <div>
          <span className="text-xs uppercase tracking-wide text-muted">Version</span>
          <div>{meta.fc_version ?? "—"}</div>
        </div>
        <div>
          <span className="text-xs uppercase tracking-wide text-muted">API</span>
          <div>{meta.api_version ?? "—"}</div>
        </div>
      </div>
      <div className="grid grid-cols-3 gap-3 text-center text-sm">
        <Stat label="Loop Hz" value={loopHz.toFixed(1)} sub={`${cycleUs.toFixed(1)} µs`} />
        <Stat label="Jitter" value={`${jitter.toFixed(1)} µs`} />
        <Stat label="VBAT" value={`${vbat.toFixed(1)} V`} sub={`${amps.toFixed(2)} A`} />
      </div>
      <div className="grid grid-cols-3 gap-2">
        <Sparkline data={history.cycle_us.slice(-60)} color="#38bdf8" />
        <Sparkline data={history.vbat.slice(-60)} color="#facc15" />
        <Sparkline data={history.amps.slice(-60)} color="#fb7185" />
      </div>
      <div className="flex flex-wrap gap-2 text-xs">
        {reasons.length ? (
          reasons.map((reason) => (
            <span key={reason} className="chip chip-muted">
              {formatReason(reason)}
            </span>
          ))
        ) : (
          <span className="text-muted">Telemetry healthy</span>
        )}
      </div>
      <div className="flex justify-between gap-2 text-sm">
        <button className="btn-secondary flex-1" onClick={(e) => { e.preventDefault(); onRetest(); }}>
          Retest
        </button>
        <Link className="btn-outline flex-1 text-center" to={`/device/${device.uid ?? device.port}`}>
          Details
        </Link>
      </div>
    </div>
  );
}

function Stat({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="space-y-1">
      <div className="text-xs uppercase tracking-wide text-muted">{label}</div>
      <div className="text-lg font-semibold">{value}</div>
      {sub && <div className="text-xs text-muted">{sub}</div>}
    </div>
  );
}

function deriveStatus(device: DeviceSnapshot): "ok" | "fail" | "testing" {
  if (device.state === "testing") return "testing";
  if (device.ok === false) return "fail";
  if (device.ok === true) return "ok";
  return "testing";
}

function statusLabel(status: "ok" | "fail" | "testing") {
  if (status === "ok") return "OK";
  if (status === "fail") return "NOT OK";
  return "Testing";
}

function formatReason(reason: string): string {
  const [key, detail] = reason.split(" ", 2);
  const map: Record<string, string> = {
    loop_jitter: "Loop jitter",
    gyro_std_x: "Gyro σ X",
    gyro_std_y: "Gyro σ Y",
    gyro_std_z: "Gyro σ Z",
    gyro_bias_x: "Gyro bias X",
    gyro_bias_y: "Gyro bias Y",
    gyro_bias_z: "Gyro bias Z",
    acc_norm_std: "Accel σ",
    i2c_err: "I²C errors",
    vbat_low: "VBAT low",
    amps_high: "Current high",
    tilt: "Tilt",
  };
  return map[key] ? `${map[key]} ${detail ?? ""}`.trim() : reason;
}
