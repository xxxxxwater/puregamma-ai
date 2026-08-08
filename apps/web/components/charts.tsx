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
const positiveFill = "color-mix(in srgb, var(--positive) 12%, transparent)";
const warningFill = "color-mix(in srgb, var(--warning) 12%, transparent)";

type Point = { date: string; nav?: number; equity?: number; drawdown?: number; value?: number; confidence?: number; health?: number };
type AllocationPoint = { name: string; value: number; weight?: number };

export function ChartTooltip({ active, payload, label }: { active?: boolean; payload?: { value: number; name: string }[]; label?: string }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="border border-border-pg bg-bg-panel px-3 py-2 text-xs rounded-lg">
      <div className="mb-1 text-text-pg-muted">{label}</div>
      {payload.map((item) => <div key={item.name} className="text-text-pg">{item.name}: {Number(item.value).toLocaleString()}</div>)}
    </div>
  );
}

export function NavHistoryChart({ data }: { data: Point[] }) {
  return (
    <div className="h-72 select-none touch-pan-y">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 18, right: 4, bottom: 8, left: 4 }}>
          <XAxis dataKey="date" hide />
          <YAxis domain={["dataMin", "dataMax"]} hide />
          <Tooltip cursor={{ stroke: "var(--border-strong)", strokeWidth: 1 }} content={<ChartTooltip />} />
          <Line type="monotoneX" dataKey="nav" stroke={positive} strokeWidth={2.5} dot={false} activeDot={{ r: 4, fill: positive, stroke: "var(--background)", strokeWidth: 2 }} animationDuration={450} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

export function AllocationChart({ data }: { data: AllocationPoint[] }) {
  const colors = [white, "var(--info)", text, gray, "var(--muted-2)"];
  return (
    <div className="h-64">
      <ResponsiveContainer width="100%" height="100%">
        <PieChart>
          <Pie data={data} dataKey="weight" nameKey="name" innerRadius={58} outerRadius={86} paddingAngle={3}>
            {data.map((_, index) => <Cell key={index} fill={colors[index % colors.length]} />)}
          </Pie>
          <Tooltip content={<ChartTooltip />} />
        </PieChart>
      </ResponsiveContainer>
    </div>
  );
}

export function CreditUsageChart({ data }: { data: Point[] }) {
  return (
    <div className="h-56">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data}>
          <CartesianGrid stroke={grid} vertical={false} />
          <XAxis dataKey="date" stroke={text} tickLine={false} axisLine={false} />
          <YAxis stroke={text} tickLine={false} axisLine={false} />
          <Tooltip content={<ChartTooltip />} />
          <Bar dataKey="value" fill={white} radius={[6, 6, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

export function ConfidenceDistributionChart({ data }: { data: Point[] }) {
  return (
    <div className="h-64">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 12, right: 6, bottom: 8, left: -18 }} barCategoryGap="28%">
          <CartesianGrid stroke={grid} vertical={false} />
          <XAxis dataKey="date" stroke={text} tickLine={false} axisLine={false} interval={0} minTickGap={10} />
          <YAxis stroke={text} tickLine={false} axisLine={false} width={36} domain={[0, 100]} />
          <Tooltip content={<ChartTooltip />} />
          <Bar dataKey="confidence" fill={white} radius={[6, 6, 0, 0]} maxBarSize={44} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

export function EquityCurveChart({ data }: { data: Point[] }) {
  return (
    <div className="h-64">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data}>
          <CartesianGrid stroke={grid} vertical={false} />
          <XAxis dataKey="date" stroke={text} tickLine={false} axisLine={false} />
          <YAxis stroke={text} tickLine={false} axisLine={false} />
          <Tooltip content={<ChartTooltip />} />
          <Area type="monotone" dataKey="equity" stroke={white} fill={whiteFill} strokeWidth={2} />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

export function DrawdownChart({ data }: { data: Point[] }) {
  return (
    <div className="h-48">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data}>
          <CartesianGrid stroke={grid} vertical={false} />
          <XAxis dataKey="date" stroke={text} tickLine={false} axisLine={false} />
          <YAxis stroke={text} tickLine={false} axisLine={false} />
          <Tooltip content={<ChartTooltip />} />
          <Area type="monotone" dataKey="drawdown" stroke={negative} fill={negativeFill} strokeWidth={2} />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

export function HealthTimelineChart({ data }: { data: Point[] }) {
  return (
    <div className="h-48">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data}>
          <CartesianGrid stroke={grid} vertical={false} />
          <XAxis dataKey="date" stroke={text} tickLine={false} axisLine={false} />
          <YAxis stroke={text} tickLine={false} axisLine={false} />
          <Tooltip content={<ChartTooltip />} />
          <Line type="monotone" dataKey="health" stroke={warning} strokeWidth={2} dot={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
