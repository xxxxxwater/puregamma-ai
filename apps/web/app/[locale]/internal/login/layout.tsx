import type { Metadata } from "next";
import type { ReactNode } from "react";


export const metadata: Metadata = {
  title: "PureGamma Internal",
  robots: { index: false, follow: false, nocache: true },
};


export default function InternalAdminLoginLayout({ children }: { children: ReactNode }) {
  return children;
}
