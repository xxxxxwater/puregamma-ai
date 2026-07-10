import { redirect } from "next/navigation";
import { getPreferredLocale } from "@/i18n/request";

export default function RootPage() {
  redirect(`/${getPreferredLocale()}`);
}
