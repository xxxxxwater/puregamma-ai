"use client";

import { ReportMarkdown } from "@/components/puregamma";

export function Markdown({ content }: { content: string }) {
  return <ReportMarkdown content={content} />;
}
