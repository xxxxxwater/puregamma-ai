"use client";

import { Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, Line, LineChart, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

const grid = "var(--border)";
const text = "var(--muted)";
const white = "var(--foreground)";
const gray = "var(--muted-2)";
const positive = "var(--positive)";
const negative = "var(--negative)";
const warning = "var(--warning)";
const whiteFill = "color-mix(in srgb, var(--foreground) 8%, transparent)";
const negativeFill = "color-mix(in srgb, var(--negative) 12%, transparent)";

type Point = { date: string; nav?: number; equity?: number; drawdown?: number; value?: number; confidence?: number; health?: number };
type AllocationPoint = { name: string; value: number; weight?: number };

const lineCursor = { stroke: "var(--border-strong)", strokeWidth: 1 };
const barCursor = { fill: "color-mix(in srgb, var(--foreground) 4%, transparent)" };
const axisTick = { fontSize: 11 };

function formatChartValue(value: number) {
  if (!Number.isFinite(value)) return "—";
  return value.toLocaleString(undefined, { maximumFractionDigits: 2 });
}

export function ChartTooltip({ active, payload, label }: { active?: boolean; payload?: { value: number; name: string }[]; label?: string }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="apple-chart-tooltip">
      {label ? <div className="apple-chart-tooltip-label">{label}</div> : null}
      {payload.map((item) => (
        <div key={item.name} className="apple-chart-tooltip-row">
          <span className="apple-chart-tooltip-name">{item.name}</span>
          <span className="apple-chart-tooltip-value">{formatChartValue(Number(item.value))}</span>
        </div>
      ))}
    </div>
  );
}

export function NavHistoryChart({ data }: { data: Point[] }) {
  return (
    <div className="apple-financial-chart h-72 select-none">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 18, right: 4, bottom: 8, left: 4 }}>
          <XAxis dataKey="date" hide />
          <YAxis domain={["dataMin", "dataMax"]} hide />
          <Tooltip cursor={lineCursor} content={<ChartTooltip />} isAnimationActive={false} />
          <Line type="monotoneX" dataKey="nav" stroke={positive} strokeWidth={2.25} dot={false} activeDot={{ r: 3.5, fill: positive, stroke: "var(--background)", strokeWidth: 2 }} isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

export function AllocationChart({ data }: { data: AllocationPoint[] }) {
  const colors = [white, "var(--info)", text, gray, "var(--muted-2)"];
  return (
    <div className="apple-financial-chart h-64 select-none">
      <ResponsiveContainer width="100%" height="100%">
        <PieChart>
          <Pie data={data} dataKey="weight" nameKey="name" innerRadius={58} outerRadius={86} paddingAngle={3} isAnimationActive={false}>
            {data.map((_, index) => <Cell key={index} fill={colors[index % colors.length]} />)}
          </Pie>
          <Tooltip content={<ChartTooltip />} isAnimationActive={false} />
        </PieChart>
      </ResponsiveContainer>
    </div>
  );
}

export function CreditUsageChart({ data }: { data: Point[] }) {
  return (
    <div className="apple-financial-chart h-56 select-none">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data}>
          <CartesianGrid stroke={grid} vertical={false} />
          <XAxis dataKey="date" stroke={text} tick={axisTick} tickLine={false} axisLine={false} />
          <YAxis stroke={text} tick={axisTick} tickLine={false} axisLine={false} />
          <Tooltip cursor={barCursor} content={<ChartTooltip />} isAnimationActive={false} />
          <Bar dataKey="value" fill={white} radius={[6, 6, 0, 0]} isAnimationActive={false} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

export function ConfidenceDistributionChart({ data }: { data: Point[] }) {
  return (
    <div className="apple-financial-chart h-64 select-none">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 12, right: 6, bottom: 8, left: -18 }} barCategoryGap="28%">
          <CartesianGrid stroke={grid} vertical={false} />
          <XAxis dataKey="date" stroke={text} tick={axisTick} tickLine={false} axisLine={false} interval={0} minTickGap={10} />
          <YAxis stroke={text} tick={axisTick} tickLine={false} axisLine={false} width={36} domain={[0, 100]} />
          <Tooltip cursor={barCursor} content={<ChartTooltip />} isAnimationActive={false} />
          <Bar dataKey="confidence" fill={white} radius={[6, 6, 0, 0]} maxBarSize={44} isAnimationActive={false} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

export function EquityCurveChart({ data }: { data: Point[] }) {
  return (
    <div className="apple-financial-chart h-64 select-none">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data}>
          <CartesianGrid stroke={grid} vertical={false} />
          <XAxis dataKey="date" stroke={text} tick={axisTick} tickLine={false} axisLine={false} />
          <YAxis stroke={text} tick={axisTick} tickLine={false} axisLine={false} />
          <Tooltip cursor={lineCursor} content={<ChartTooltip />} isAnimationActive={false} />
          <Area type="monotone" dataKey="equity" stroke={white} fill={whiteFill} strokeWidth={2} activeDot={{ r: 3.5, fill: white, stroke: "var(--background)", strokeWidth: 2 }} isAnimationActive={false} />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

export function DrawdownChart({ data }: { data: Point[] }) {
  return (
    <div className="apple-financial-chart h-48 select-none">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data}>
          <CartesianGrid stroke={grid} vertical={false} />
          <XAxis dataKey="date" stroke={text} tick={axisTick} tickLine={false} axisLine={false} />
          <YAxis stroke={text} tick={axisTick} tickLine={false} axisLine={false} />
          <Tooltip cursor={lineCursor} content={<ChartTooltip />} isAnimationActive={false} />
          <Area type="monotone" dataKey="drawdown" stroke={negative} fill={negativeFill} strokeWidth={2} activeDot={{ r: 3.5, fill: negative, stroke: "var(--background)", strokeWidth: 2 }} isAnimationActive={false} />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

export function HealthTimelineChart({ data }: { data: Point[] }) {
  return (
    <div className="apple-financial-chart h-48 select-none">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data}>
          <CartesianGrid stroke={grid} vertical={false} />
          <XAxis dataKey="date" stroke={text} tick={axisTick} tickLine={false} axisLine={false} />
          <YAxis stroke={text} tick={axisTick} tickLine={false} axisLine={false} />
          <Tooltip cursor={lineCursor} content={<ChartTooltip />} isAnimationActive={false} />
          <Line type="monotone" dataKey="health" stroke={warning} strokeWidth={2} dot={false} activeDot={{ r: 3.5, fill: warning, stroke: "var(--background)", strokeWidth: 2 }} isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
