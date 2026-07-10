import { redirectToLocalized } from "@/app/legacy-redirect";

export default function BillingCancelRedirect() {
  redirectToLocalized("/billing/cancel");
}
