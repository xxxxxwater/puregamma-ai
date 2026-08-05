import { redirect } from "next/navigation";
import { getPreferredLocaleGeo } from "@/i18n/request";

export default async function RootPage() {
  redirect(`/${await getPreferredLocaleGeo()}`);
}
