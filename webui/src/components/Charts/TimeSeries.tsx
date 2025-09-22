import { useEffect, useRef } from "react";
import * as echarts from "echarts";

type Props = {
  title: string;
  data: number[];
  color?: string;
};

export default function TimeSeries({ title, data, color = "#38bdf8" }: Props) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!ref.current) return;
    const chart = echarts.init(ref.current, null, { renderer: "svg" });
    chart.setOption({
      title: { text: title, textStyle: { color: "#cbd5f5", fontSize: 12 } },
      grid: { left: 32, right: 8, top: 24, bottom: 24 },
      xAxis: { type: "category", boundaryGap: false, show: false, data: data.map((_, idx) => idx) },
      yAxis: { type: "value", axisLine: { lineStyle: { color: "#475569" } }, splitLine: { show: false } },
      series: [
        {
          type: "line",
          data: data.length ? data : [0],
          smooth: true,
          showSymbol: false,
          lineStyle: { color, width: 2 },
          areaStyle: { opacity: 0.15, color },
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
