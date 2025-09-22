import { useEffect, useRef } from "react";
import * as echarts from "echarts";

type Props = {
  title: string;
  data: number[];
  color?: string;
};

export default function Histogram({ title, data, color = "#f97316" }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!ref.current) return;
    const chart = echarts.init(ref.current, null, { renderer: "svg" });
    const values = data.length ? data : [0];
    const bins = 15;
    const min = Math.min(...values);
    const max = Math.max(...values);
    const step = bins > 0 ? (max - min) / bins || 1 : 1;
    const histogram = new Array(bins).fill(0);
    values.forEach((value) => {
      const idx = Math.min(bins - 1, Math.max(0, Math.floor((value - min) / step)));
      histogram[idx] += 1;
    });
    chart.setOption({
      title: { text: title, textStyle: { color: "#cbd5f5", fontSize: 12 } },
      grid: { left: 32, right: 8, top: 24, bottom: 24 },
      xAxis: {
        type: "category",
        data: histogram.map((_, idx) => (min + idx * step).toFixed(1)),
        show: false,
      },
      yAxis: { type: "value", show: false },
      series: [
        {
          type: "bar",
          data: histogram,
          itemStyle: { color },
        }
      ]
    });
    const handle = () => chart.resize();
    window.addEventListener("resize", handle);
    return () => {
      window.removeEventListener("resize", handle);
      chart.dispose();
    };
  }, [title, data, color]);

  return <div ref={ref} className="h-48 w-full" />;
}
