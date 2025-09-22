import { useEffect, useRef } from "react";
import * as echarts from "echarts";

type Props = {
  value: number;
};

export default function Sparkline({ value }: Props) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!ref.current) return;
    const chart = echarts.init(ref.current, null, { renderer: "svg" });
    chart.setOption({
      grid: { left: 0, right: 0, top: 0, bottom: 0 },
      xAxis: { type: "category", show: false, data: ["now"] },
      yAxis: { type: "value", show: false },
      series: [
        {
          type: "line",
          data: [value],
          smooth: true,
          areaStyle: {},
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
  }, [value]);

  return <div ref={ref} className="h-16 w-full" />;
}
