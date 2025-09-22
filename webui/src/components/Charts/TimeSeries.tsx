import { useEffect, useRef } from "react";
import * as echarts from "echarts";

type Props = {
  title: string;
  value: number;
};

export default function TimeSeries({ title, value }: Props) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!ref.current) return;
    const chart = echarts.init(ref.current, null, { renderer: "svg" });
    const data = Array.from({ length: 20 }, (_, idx) => ({ value: value + Math.sin(idx) }));
    chart.setOption({
      title: { text: title, textStyle: { color: "#cbd5f5", fontSize: 12 } },
      grid: { left: 32, right: 8, top: 24, bottom: 24 },
      xAxis: { type: "category", boundaryGap: false, show: false },
      yAxis: { type: "value", axisLine: { lineStyle: { color: "#475569" } }, splitLine: { show: false } },
      series: [
        {
          type: "line",
          data: data.map((d) => d.value),
          smooth: true,
          showSymbol: false,
          lineStyle: { color: "#38bdf8" },
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
