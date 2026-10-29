"use client";

import { useState } from "react";
import { Eye, EyeOff } from "lucide-react";
import { Button } from "@/components/ui";

export function PasswordInput({
  value,
  onChange,
  placeholder,
  minLength,
  autoComplete,
}: {
  value: string;
  onChange: (value: string) => void;
  placeholder: string;
  minLength?: number;
  autoComplete?: string;
}) {
  const [visible, setVisible] = useState(false);
  return (
    <div className="relative">
      <input
        type={visible ? "text" : "password"}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        className="w-full border border-border-pg bg-bg-panel-muted px-3 py-2 pr-10 text-sm text-text-pg placeholder:text-text-pg-dim outline-none focus:border-border-pg-strong rounded-lg"
        required
        minLength={minLength}
        autoComplete={autoComplete}
      />
      <Button variant="ghost"
        type="button"
        onClick={() => setVisible((current) => !current)}
        aria-label={visible ? "Hide password" : "Show password"}
        aria-pressed={visible}
        className="absolute right-2 top-1/2 -translate-y-1/2 p-1"
      >
        {visible ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
      </Button>
    </div>
  );
}
