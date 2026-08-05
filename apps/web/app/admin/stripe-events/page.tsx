import { redirectToLocalized } from "@/app/legacy-redirect";

export default function StripeEventsRedirect() {
  redirectToLocalized("/admin/stripe-events");
}
