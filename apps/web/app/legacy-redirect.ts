import { redirect } from "next/navigation";
import { getPreferredLocale } from "@/i18n/request";
import { withLocale } from "@/i18n/routing";

export function redirectToLocalized(path: string): never {
  redirect(withLocale(getPreferredLocale(), path));
}
