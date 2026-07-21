import { redirectToLocalized } from "@/app/legacy-redirect";

export default function VerifyEmailRedirect() {
  redirectToLocalized("/verify-email");
}
