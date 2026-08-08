import type { Locale } from "@/i18n/routing";

const PRIVACY_URL = "https://puregamma.ai/privacy";
const TERMS_URL = "https://puregamma.ai/terms";

export function AuthLegalNotice({ locale, mode }: { locale: Locale; mode: "login" | "signup" }) {
  const zh = locale === "zh";
  const linkClass = "font-medium text-text-pg underline underline-offset-2 hover:text-text-pg-muted";

  return (
    <p className="text-center text-xs leading-5 text-text-pg-dim">
      {mode === "signup" ? (
        <>
          {zh ? "创建账户即表示你同意" : "By creating an account, you agree to our "}
          <a className={linkClass} href={TERMS_URL} target="_blank" rel="noreferrer">
            {zh ? "服务条款" : "Terms of Service"}
          </a>
          {zh ? "并确认已阅读" : " and acknowledge our "}
          <a className={linkClass} href={PRIVACY_URL} target="_blank" rel="noreferrer">
            {zh ? "隐私政策" : "Privacy Policy"}
          </a>
          {zh ? "。" : "."}
        </>
      ) : (
        <>
          {zh ? "继续使用 Google 登录即表示你同意" : "By continuing with Google, you agree to our "}
          <a className={linkClass} href={TERMS_URL} target="_blank" rel="noreferrer">
            {zh ? "服务条款" : "Terms of Service"}
          </a>
          {zh ? "并确认已阅读" : " and acknowledge our "}
          <a className={linkClass} href={PRIVACY_URL} target="_blank" rel="noreferrer">
            {zh ? "隐私政策" : "Privacy Policy"}
          </a>
          {zh ? "。" : "."}
        </>
      )}
    </p>
  );
}
