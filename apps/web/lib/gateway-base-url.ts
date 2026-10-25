"use client";

import { useEffect, useState } from "react";
import { apiBaseUrl } from "@/lib/api";

/** Match copyable Gateway examples to this Web deployment's API edge. */
export function useGatewayBaseUrl(): string {
  // Keep server rendering and hydration identical when the API URL is relative.
  const configuredApiUrl = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/+$/, "");
  const [baseUrl, setBaseUrl] = useState(`${configuredApiUrl}/v1`);

  useEffect(() => {
    setBaseUrl(`${apiBaseUrl().replace(/\/+$/, "")}/v1`);
  }, []);

  return baseUrl;
}
