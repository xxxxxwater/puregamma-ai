import { redirectToLocalized } from "@/app/legacy-redirect";

export default function GatewayAdministrationRedirect() {
  redirectToLocalized("/admin/gateway");
}
