import { redirectToLocalized } from "@/app/legacy-redirect";

export default function BillingIntentsRedirect() {
  redirectToLocalized("/admin/billing-intents");
}
