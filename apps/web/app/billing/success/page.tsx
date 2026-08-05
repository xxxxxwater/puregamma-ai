import { redirectToLocalized } from "@/app/legacy-redirect";

export default function BillingSuccessRedirect() {
  redirectToLocalized("/billing/success");
}
