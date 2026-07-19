import type { Metadata } from "next";
import { PublicLegalPage, type PublicLegalSection } from "@/components/public-legal-page";

export const metadata: Metadata = {
  title: "Terms of Service — PureGamma AI",
  description: "PureGamma AI terms of service and research risk disclosure.",
  alternates: { canonical: "https://puregamma.ai/terms" },
};

const sections: PublicLegalSection[] = [
  {
    title: "服务范围 / Scope",
    body: <><p>PureGamma 提供市场研究、带来源的报告、组合分析、风险辅助和受控的 AI 决策支持。</p><p>PureGamma is not a broker, exchange, investment adviser, custodian, or fiduciary. The service does not withdraw or transfer user funds and does not request seed phrases or private keys.</p></>,
  },
  {
    title: "研究与投资风险 / Research and investment risk",
    body: <><p>Market data may be delayed, incomplete, stale, or unavailable. AI-generated content can contain errors. Digital assets, equities, options, and derivatives can lose substantial value.</p><p>所有内容仅供研究和信息用途，不构成投资、税务、法律或财务建议。用户独立承担投资决策和损失风险。</p></>,
  },
  {
    title: "账号与安全 / Accounts and security",
    body: <><p>You are responsible for protecting your device and account access. Do not submit private keys, seed phrases, trading credentials, or information you are not authorized to share.</p><p>为保护用户和平台，PureGamma 可以限制异常、滥用、未经授权或违反适用法律的访问。</p></>,
  },
  {
    title: "套餐与 Credits / Plans and Credits",
    body: <><p>套餐权限、Credits、并发限制和数据源授权由服务端记录决定。Web 订阅通过批准的支付渠道管理。</p><p>Credits are usage units for eligible PureGamma features and are not cash, stored value, or a transferable financial instrument.</p></>,
  },
  {
    title: "服务可用性与责任 / Availability and liability",
    body: <><p>The service is provided on an as-available basis. To the maximum extent permitted by law, PureGamma is not liable for trading losses, missed opportunities, third-party outages, or reliance on generated research.</p><p>适用法律不允许排除或限制的消费者权利与责任不受本条限制。</p></>,
  },
  {
    title: "联系 / Contact",
    body: <p>条款相关问题 / Questions about these terms: <a href="mailto:hello@puregamma.ai">hello@puregamma.ai</a>.</p>,
  },
];

export default function TermsPage() {
  return <PublicLegalPage eyebrow="TERMS / 条款" title={"Terms of Service\n服务条款"} updated="2026-07-19" sections={sections} />;
}
