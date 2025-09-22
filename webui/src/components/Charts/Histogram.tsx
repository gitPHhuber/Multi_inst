import { useEffect, useRef } from "react";
import * as echarts from "echarts";

type Props = {
  title: string;
  value: number;
};

export default function Histogram({ title, value }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!ref.current) return;
    const chart = echarts.init(ref.current, null, { renderer: "svg" });
    const bins = Array.from({ length: 10 }, (_, idx) => value + idx * 0.2);
    chart.setOption({
      title: { text: title, textStyle: { color: "#cbd5f5", fontSize: 12 } },
      grid: { left: 32, right: 8, top: 24, bottom: 24 },
      xAxis: { type: "category", data: bins.map((_, idx) => idx), show: false },
      yAxis: { type: "value", show: false },
      series: [
        {
          type: "bar",
          data: bins.map((bin, idx) => Math.max(0.1, Math.sin(idx) + 0.5)),
          itemStyle: { color: "#f97316" },
        }
      ]
    });
    const handle = () => chart.resize();
    window.addEventListener("resize", handle);
    return () => {
      window.removeEventListener("resize", handle);
      chart.dispose();
    };
  }, [title, value]);

  return <div ref={ref} className="h-48 w-full" />;
}
