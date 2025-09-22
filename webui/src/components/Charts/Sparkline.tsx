import { useEffect, useRef } from "react";
import * as echarts from "echarts";

type Props = {
  data: number[];
  color?: string;
};

export default function Sparkline({ data, color }: Props) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!ref.current) return;
    const chart = echarts.init(ref.current, null, { renderer: "svg" });
    chart.setOption({
      grid: { left: 0, right: 0, top: 0, bottom: 0 },
      xAxis: { type: "category", show: false, data: data.map((_, idx) => idx) },
      yAxis: { type: "value", show: false },
      series: [
        {
          type: "line",
          data: data.length ? data : [0],
          smooth: true,
          areaStyle: { opacity: 0.2 },
          lineStyle: { width: 2, color: color ?? "#38bdf8" },
          itemStyle: { color: color ?? "#38bdf8" },
          showSymbol: false,
        }
      ]
    });
    const handle = () => {
      chart.resize();
    };
    window.addEventListener("resize", handle);
    return () => {
      window.removeEventListener("resize", handle);
      chart.dispose();
    };
  }, [data, color]);

  return <div ref={ref} className="h-16 w-full" />;
}
