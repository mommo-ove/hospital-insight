import { useEffect, useRef } from 'react';
import * as echarts from 'echarts/core';
import { BarChart, LineChart } from 'echarts/charts';
import { GridComponent, TooltipComponent, LegendComponent } from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';
import type { Answer, Column } from './types';

echarts.use([BarChart, LineChart, GridComponent, TooltipComponent, LegendComponent, CanvasRenderer]);

export default function QueryChart({ answer, metric }: { answer: Answer; metric: Column }) {
  const element = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!element.current || !answer.chart) return;
    const chart = echarts.init(element.current);
    const spec = answer.chart;
    const seriesDimensions = spec.dimensions.filter(d => d !== 'month');
    const categories = spec.type === 'line' ? [...new Set(spec.rows.map(r => String(r.month)))].sort() : spec.rows.map(r => spec.dimensions.map(d => r[d]).join(' · '));
    const seriesNames = spec.type === 'line' && seriesDimensions.length ? [...new Set(spec.rows.map(r => seriesDimensions.map(d => r[d]).join(' · ')))] : [metric.label];
    chart.setOption({
      color: ['#23816b', '#629cb4', '#c2a76f', '#9d8ac0', '#6a8d70', '#d59483', '#567b95', '#b7ba7a'],
      tooltip: { trigger: 'axis', renderMode: 'richText', confine: true },
      legend: { show: seriesNames.length > 1, bottom: 0, type: 'scroll' },
      grid: { top: 36, left: 18, right: 20, bottom: seriesNames.length > 1 ? 48 : 22, containLabel: true },
      xAxis: { type: 'category', data: categories, axisLine: { lineStyle: { color: '#dfe6e2' } }, axisTick: { show: false }, axisLabel: { color: '#7b8982', fontSize: 11, interval: 0, rotate: categories.length > 8 ? 32 : 0 } },
      yAxis: { type: 'value', name: metric.unit, nameTextStyle: { color: '#7b8982' }, splitLine: { lineStyle: { color: '#edf1ef', type: 'dashed' } }, axisLabel: { color: '#7b8982', formatter: (v: number) => Math.abs(v) >= 10000 ? `${+(v / 10000).toFixed(2)}万` : String(v) } },
      series: seriesNames.map(name => ({
        name, type: spec.type, smooth: false, symbolSize: 6, barMaxWidth: 38,
        itemStyle: spec.type === 'bar' ? { borderRadius: [5, 5, 0, 0] } : {},
        areaStyle: spec.type === 'line' && seriesNames.length === 1 ? { opacity: 0.06 } : undefined,
        data: spec.type === 'bar' ? spec.rows.map(r => r[metric.key]) : categories.map(month => {
          const row = spec.rows.find(r => String(r.month) === month && (seriesNames.length === 1 && !seriesDimensions.length || seriesDimensions.map(d => r[d]).join(' · ') === name));
          return row?.[metric.key] ?? null;
        }),
      })),
    });
    const observer = new ResizeObserver(() => chart.resize());
    observer.observe(element.current);
    return () => { observer.disconnect(); chart.dispose(); };
  }, [answer, metric]);
  return <div ref={element} className="query-chart" role="img" aria-label={`${metric.label}${answer.chart?.type === 'line' ? '趋势图' : '比较图'}，具体数值见结果表`} />;
}
