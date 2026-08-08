import type { ReactNode } from "react";

type Column<T> = {
  key: string;
  header: ReactNode;
  align?: "left" | "right";
  render: (row: T) => ReactNode;
};

export function PGTable<T>({ columns, rows, minWidth = 720, empty }: { columns: Column<T>[]; rows: T[]; minWidth?: number; empty?: ReactNode }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm" style={{ minWidth }}>
        <thead>
          <tr className="border-y border-border-pg text-left text-xs text-text-pg-muted rounded-lg">
            {columns.map((column) => <th key={column.key} className={`px-3 py-2 font-medium ${column.align === "right" ? "text-right" : ""}`}>{column.header}</th>)}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={index} className="border-b border-border-pg last:border-0">
              {columns.map((column) => <td key={column.key} className={`px-3 py-3 ${column.align === "right" ? "text-right" : ""}`}>{column.render(row)}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
      {!rows.length && empty ? <div className="p-4">{empty}</div> : null}
    </div>
  );
}
