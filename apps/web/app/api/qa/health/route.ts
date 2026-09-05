import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";

export function GET() {
  if (process.env.NODE_ENV === "production" && process.env.ENABLE_QA_SURFACES !== "true") {
    return new NextResponse(null, { status: 404 });
  }
  return NextResponse.json({ ok: true, surface: "agent-fluid" });
}
