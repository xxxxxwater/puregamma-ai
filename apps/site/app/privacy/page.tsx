import type { Metadata } from "next";
import { LegalPage, type LegalSection } from "../legal-page";

export const metadata: Metadata = { title: "Privacy Policy — PureGamma AI", description: "PureGamma AI privacy policy and data choices." };

const sections: LegalSection[] = [
  { title: "我们收集的数据 / Data we collect", body: <><p>我们会处理建立账号所需的姓名、电子邮件、登录标识，以及用户主动提交的研究提示、附件和偏好。</p><p>When you connect an account, we process read-only portfolio balances, positions, account status and history needed to provide portfolio research. We do not request private keys, seed phrases, wallet signatures, transfer or withdrawal authority.</p></> },
  { title: "使用目的 / How data is used", body: <><p>数据仅用于认证、提供行情与研究、生成用户请求的 Agent 回答、展示组合信息、执行额度与套餐权限，以及发送用户启用的通知。</p><p>We do not sell personal data or use portfolio data for cross-app advertising. Model and data providers receive only the information necessary for the requested feature and subject to server-side access controls.</p></> },
  { title: "第三方服务 / Service providers", body: <><p>PureGamma may use Apple and Google for authentication, Plaid and supported brokers for read-only account connections, market-data providers, infrastructure providers, and Stripe or the App Store for billing. Their own privacy terms also apply.</p><p>第三方 Secret、交易所 Secret、Plaid/IBKR 凭据和模型密钥仅保存在服务端受控环境，不会写入 iOS 客户端。</p></> },
  { title: "保留与安全 / Retention and security", body: <><p>We retain account data while the account is active and as needed for security, fraud prevention, billing records, and legal obligations. Bearer tokens are stored in the iOS Keychain; provider credentials are encrypted server-side.</p><p>任何互联网系统均无法保证绝对安全。发现安全问题请联系 hello@puregamma.ai。</p></> },
  { title: "用户权利 / Your choices", body: <><p>You can change language, appearance and notification preferences in the app. You can disconnect portfolio providers and initiate permanent account deletion from Account settings. Deletion removes associated personal data unless retention is legally required.</p><p>如需访问、更正、导出或删除数据，请使用 App 内功能或联系 hello@puregamma.ai。</p></> },
  { title: "联系 / Contact", body: <p>Privacy questions and requests: <a className="textLink" href="mailto:hello@puregamma.ai">hello@puregamma.ai</a>.</p> },
];

export default function PrivacyPage() { return <LegalPage eyebrow="PRIVACY / 隐私" title="Privacy Policy\n隐私政策" updated="2026-07-15" sections={sections} />; }
