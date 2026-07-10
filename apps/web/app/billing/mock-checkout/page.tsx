import { redirect } from "next/navigation";
import { getPreferredLocale } from "@/i18n/request";
import { withLocale } from "@/i18n/routing";

export default function MockCheckoutRedirect({
  searchParams,
}: {
  searchParams: { session?: string; plan?: string };
}) {
  const params = new URLSearchParams();
  if (searchParams.session) params.set("session", searchParams.session);
  if (searchParams.plan) params.set("plan", searchParams.plan);
  const query = params.toString();
  redirect(withLocale(getPreferredLocale(), `/billing/mock-checkout${query ? `?${query}` : ""}`));
}
