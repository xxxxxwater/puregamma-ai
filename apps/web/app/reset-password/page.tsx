import { redirectToLocalized } from "@/app/legacy-redirect";

export default function ResetPasswordRedirect() {
  redirectToLocalized("/reset-password");
}
