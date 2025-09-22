import Sparkline from "./Charts/Sparkline";

type Props = {
  device: any;
};

export default function DeviceCard({ device }: Props) {
  const ok = device.ok !== false;
  const statusColor = ok ? "text-emerald-400" : "text-rose-400";
  const volt = device.analog?.vbat_V ?? 0;
  const amps = device.analog?.amps_A ?? 0;
  const loopHz = device.loop_stats?.loop_hz_mean ?? 0;
  return (
    <div className="card">
      <div className="flex items-center justify-between">
        <div>
          <div className="text-sm text-slate-400">{device.port}</div>
          <div className="text-lg font-semibold">{device.uid}</div>
        </div>
        <div className={statusColor}>{ok ? "OK" : "FAIL"}</div>
      </div>
      <div className="mt-4 grid grid-cols-3 gap-2 text-center text-sm">
        <div>
          <div className="text-slate-400">Loop Hz</div>
          <div className="font-medium">{loopHz.toFixed(1)}</div>
        </div>
        <div>
          <div className="text-slate-400">VBAT</div>
          <div className="font-medium">{volt.toFixed(1)} V</div>
        </div>
        <div>
          <div className="text-slate-400">Current</div>
          <div className="font-medium">{amps.toFixed(1)} A</div>
        </div>
      </div>
      <div className="mt-4">
        <Sparkline value={loopHz} />
      </div>
    </div>
  );
}
