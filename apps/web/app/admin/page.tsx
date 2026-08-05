import { redirectToLocalized } from "@/app/legacy-redirect";

export default function AdminRedirect() {
  redirectToLocalized("/admin");
}
