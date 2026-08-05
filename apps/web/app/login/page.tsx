import { redirectToLocalized } from "@/app/legacy-redirect";

export default function LoginRedirect() {
  redirectToLocalized("/login");
}
