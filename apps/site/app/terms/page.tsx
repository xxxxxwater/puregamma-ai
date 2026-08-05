import type { Metadata } from "next";
import { LegalPage, type LegalSection } from "../legal-page";

export const metadata: Metadata = { title: "Terms of Service — PureGamma AI", description: "PureGamma AI terms of service and research risk disclosure." };

const sections: LegalSection[] = [
  { title: "服务范围 / Scope", body: <><p>PureGamma provides market research, sourced reports, options research, portfolio review and AI-assisted decision support.</p><p>本服务不是经纪商、交易所、投资顾问、托管人或受托人，不代表用户下单、转账、提现或签名钱包交易。</p></> },
  { title: "研究风险 / Research risk", body: <><p>Market data may be delayed, incomplete or unavailable. AI-generated content may contain errors. Long Gamma, derivatives, digital assets and public-market investments can lose substantial value.</p><p>所有内容仅供研究与信息用途，不构成投资、税务、法律或财务建议。用户独立承担决策和损失风险。</p></> },
  { title: "账号与安全 / Accounts", body: <><p>You are responsible for protecting your device and account access. Do not submit private keys, seed phrases, trading secrets or information you are not authorized to share.</p><p>我们可为保护用户、平台或符合法律要求而限制异常、滥用或未经授权的访问。</p></> },
  { title: "套餐与 Credits / Plans", body: <><p>Plan access, Credits, concurrency and data-source permissions are determined by the server. Apple in-app purchases, when offered, are governed by App Store purchase terms. Web subscriptions are managed separately through approved web billing channels.</p><p>客户端不得绕过 past_due、额度或权限限制。</p></> },
  { title: "可用性与责任 / Availability", body: <><p>The service is provided on an as-available basis. To the maximum extent permitted by law, PureGamma is not liable for trading losses, missed opportunities, third-party outages or reliance on generated research.</p><p>法律不允许排除的权利和责任不受本条限制。</p></> },
  { title: "联系 / Contact", body: <p>Questions about these terms: <a className="textLink" href="mailto:hello@puregamma.ai">hello@puregamma.ai</a>.</p> },
];

export default function TermsPage() { return <LegalPage eyebrow="TERMS / 条款" title="Terms of Service\n服务条款" updated="2026-07-15" sections={sections} />; }
