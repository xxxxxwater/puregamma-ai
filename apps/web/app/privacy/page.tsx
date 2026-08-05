import type { Metadata } from "next";
import { PublicLegalPage, type PublicLegalSection } from "@/components/public-legal-page";

export const metadata: Metadata = {
  title: "Privacy Policy — PureGamma AI",
  description: "PureGamma AI privacy policy and data choices.",
  alternates: { canonical: "https://puregamma.ai/privacy" },
};

const sections: PublicLegalSection[] = [
  {
    title: "我们收集的数据 / Data we collect",
    body: <><p>我们会处理建立账号所需的姓名、电子邮件、登录标识，以及用户主动提交的研究提示、附件和偏好。</p><p>When you connect an account, we process read-only portfolio balances, positions, account status, and history needed to provide portfolio research. We do not request private keys, seed phrases, wallet signatures, transfer authority, or withdrawal authority.</p></>,
  },
  {
    title: "使用目的 / How data is used",
    body: <><p>数据用于认证、提供行情与研究、生成用户请求的 Agent 回答、展示组合信息、执行 Credits 与套餐权限，以及发送用户启用的通知。</p><p>We do not sell personal data or use portfolio data for cross-app advertising. Model and data providers receive only the information needed for the feature requested by the user and are subject to server-side access controls.</p></>,
  },
  {
    title: "第三方服务 / Service providers",
    body: <><p>PureGamma may use Google and Apple for authentication, supported brokers and data connectors for read-only account connections, market-data and model providers, infrastructure providers, and Stripe or the App Store for billing. Their own privacy terms also apply.</p><p>第三方凭据、交易所 Secret、连接器 Token 和模型密钥只保存在服务端受控环境，不会返回给浏览器或交给模型。</p></>,
  },
  {
    title: "保留与安全 / Retention and security",
    body: <><p>We retain account data while an account is active and as needed for security, fraud prevention, billing records, dispute handling, and legal obligations. Security controls include access restrictions, encrypted transport, credential protection, and audit records.</p><p>任何互联网系统都无法保证绝对安全。发现安全或隐私问题请联系 hello@puregamma.ai。</p></>,
  },
  {
    title: "用户选择与权利 / Your choices",
    body: <><p>用户可以管理通知与偏好、断开组合数据连接，并通过账户功能申请删除账号。除法律要求保留的记录外，账号删除将移除相关个人数据。</p><p>To request access, correction, export, or deletion of personal data, use the account controls or contact hello@puregamma.ai.</p></>,
  },
  {
    title: "联系 / Contact",
    body: <p>隐私问题与数据请求 / Privacy questions and requests: <a href="mailto:hello@puregamma.ai">hello@puregamma.ai</a>.</p>,
  },
];

export default function PrivacyPage() {
  return <PublicLegalPage eyebrow="PRIVACY / 隐私" title={"Privacy Policy\n隐私政策"} updated="2026-07-19" sections={sections} />;
}
