import { redirectToLocalized } from "@/app/legacy-redirect";

export default function ForgotPasswordRedirect() {
  redirectToLocalized("/forgot-password");
}
