import { redirectToLocalized } from "@/app/legacy-redirect";

export default function LegacyInternalAdminLoginPage() {
  redirectToLocalized("/internal/login");
}
