import { useEffect } from "react";
import { useParams, Link } from "react-router-dom";
import { useAppStore } from "../store/useAppStore";
import TimeSeries from "./Charts/TimeSeries";
import Histogram from "./Charts/Histogram";

export default function DevicePage() {
  const { uid } = useParams();
  const { devices, refresh, sessionId } = useAppStore();
  const device = devices.find((d) => d.uid === uid);

  useEffect(() => {
    const timer = setInterval(() => refresh(), 1000);
    return () => clearInterval(timer);
  }, [refresh]);

  if (!device) {
    return (
      <div className="p-6 space-y-4">
        <Link to="/" className="text-sky-400">← Back</Link>
        <div className="text-slate-400">Device not found</div>
      </div>
    );
  }

  const loop = device.loop_stats ?? {};
  const analog = device.analog ?? {};
  const imu = device.imu_stats ?? {};

  return (
    <div className="p-6 space-y-6">
      <Link to="/" className="text-sky-400">← Back</Link>
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">{device.uid}</h1>
          <div className="text-slate-400">{device.port}</div>
        </div>
        <div className="text-sm text-slate-400">Session {sessionId}</div>
      </header>
      <section className="card space-y-2">
        <div className="font-semibold">Overview</div>
        <div className="grid grid-cols-3 gap-4 text-sm">
          <div>
            <div className="text-slate-400">Loop Hz</div>
            <div className="text-lg">{(loop.loop_hz_mean ?? 0).toFixed(1)}</div>
          </div>
          <div>
            <div className="text-slate-400">Cycle µs</div>
            <div className="text-lg">{(loop.cycle_us_mean ?? 0).toFixed(2)} ± {(loop.cycle_us_std ?? 0).toFixed(2)}</div>
          </div>
          <div>
            <div className="text-slate-400">VBAT</div>
            <div className="text-lg">{(analog.vbat_V ?? 0).toFixed(1)} V</div>
          </div>
        </div>
      </section>
      <section className="card space-y-2">
        <div className="font-semibold">Loop Timeline</div>
        <TimeSeries title="Cycle µs" value={loop.cycle_us_mean ?? 0} />
        <Histogram title="Cycle jitter" value={loop.cycle_us_std ?? 0} />
      </section>
      <section className="card space-y-2">
        <div className="font-semibold">IMU</div>
        <div className="text-sm text-slate-400">Gyro σ: {(imu.gyro_std ?? []).map((v: number) => v.toFixed(2)).join(", ")}</div>
      </section>
    </div>
  );
}
