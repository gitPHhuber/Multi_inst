import { useEffect } from "react";
import { Link } from "react-router-dom";
import { useAppStore } from "../store/useAppStore";
import DeviceCard from "./DeviceCard";

export default function Dashboard() {
  const { devices, start, refresh, sessionId } = useAppStore();

  useEffect(() => {
    if (!sessionId) {
      start();
      return;
    }
    const interval = setInterval(() => {
      refresh();
    }, 1000);
    return () => clearInterval(interval);
  }, [sessionId, refresh, start]);

  return (
    <div className="space-y-6">
      <header className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Multi Inst Dashboard</h1>
        <div className="text-sm text-slate-400">Devices {devices.length}</div>
      </header>
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {devices.map((device) => (
          <Link key={device.uid} to={`/device/${device.uid}`}>
            <DeviceCard device={device} />
          </Link>
        ))}
      </div>
    </div>
  );
}
