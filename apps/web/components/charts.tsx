"use client";

import { Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, Line, LineChart, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

const grid = "rgba(255,255,255,0.08)";
const text = "#A3A3A3";
const white = "#EDEDED";
const gray = "#737373";
const positive = "#D9F99D";
const negative = "#FCA5A5";
const warning = "#FDE68A";

type Point = { date: string; nav?: number; equity?: number; drawdown?: number; value?: number; confidence?: number; health?: number };
type AllocationPoint = { name: string; value: number; weight?: number };

function ChartTooltip({ active, payload, label }: { active?: boolean; payload?: { value: number; name: string }[]; label?: string }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="border border-border-pg bg-bg-panel px-3 py-2 text-xs">
      <div className="mb-1 text-text-pg-muted">{label}</div>
      {payload.map((item) => <div key={item.name} className="text-text-pg">{item.name}: {Number(item.value).toLocaleString()}</div>)}
    </div>
  );
}

export function NavHistoryChart({ data }: { data: Point[] }) {
  return (
    <div className="h-72">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data}>
          <CartesianGrid stroke={grid} vertical={false} />
          <XAxis dataKey="date" stroke={text} tickLine={false} axisLine={false} />
          <YAxis stroke={text} tickLine={false} axisLine={false} tickFormatter={(v) => `$${Math.round(Number(v) / 1000)}k`} />
          <Tooltip content={<ChartTooltip />} />
          <Line type="monotone" dataKey="nav" stroke={white} strokeWidth={2} dot={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

export function AllocationChart({ data }: { data: AllocationPoint[] }) {
  const colors = [white, "#D4D4D8", "#A3A3A3", "#737373", "#525252"];
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
          <Bar dataKey="value" fill={white} radius={[0, 0, 0, 0]} />
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
          <Bar dataKey="confidence" fill={white} radius={[0, 0, 0, 0]} maxBarSize={44} />
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
          <Area type="monotone" dataKey="equity" stroke={white} fill="rgba(255,255,255,0.06)" strokeWidth={2} />
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
          <Area type="monotone" dataKey="drawdown" stroke={negative} fill="rgba(252,165,165,0.08)" strokeWidth={2} />
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
