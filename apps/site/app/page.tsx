const capabilities = [
  ["01", "Research Agent", "将公开市场、组合与事件数据整理成带来源的研究结论。"],
  ["02", "Portfolio Intelligence", "统一监控资产、风险暴露、净值与数据新鲜度。"],
  ["03", "Controlled Execution", "回测、模拟盘与受控运行时分层，实盘默认关闭。"],
];

const release = [
  ["DATABASE", "Alembic baseline", "READY"],
  ["RUNTIME", "Nautilus paper mode", "READY"],
  ["WORKERS", "Redis + Celery", "READY"],
  ["PAYMENTS", "Stripe production keys", "PENDING"],
];

export default function Home() {
  return (
    <main>
      <nav className="nav shell">
        <a className="brand" href="#top" aria-label="PureGamma AI 首页">
          <span className="brandMark">PΓ</span><span>PureGamma AI</span>
        </a>
        <div className="navLinks">
          <a href="#system">系统</a><a href="#release">版本状态</a>
          <a className="button small" href="mailto:hello@puregamma.ai">申请首批访问</a>
        </div>
      </nav>

      <section id="top" className="hero shell">
        <div className="heroCopy">
          <div className="eyebrow"><span className="pulse" /> PRIVATE PREVIEW · FIRST RELEASE</div>
          <h1>把研究、组合与执行，<br /><span>放进一个可控系统。</span></h1>
          <p className="lede">PureGamma AI 是面向二级市场的智能研究与组合操作系统。它把复杂数据转化为可追溯判断，并让每一步自动化都保留边界。</p>
          <div className="actions">
            <a className="button" href="mailto:hello@puregamma.ai?subject=PureGamma%20AI%20首批访问">申请首批访问 <span>↗</span></a>
            <a className="textLink" href="#system">查看系统结构 ↓</a>
          </div>
          <p className="fine">当前为邀请制预览。非投资建议，不承诺收益。</p>
        </div>

        <div className="terminal" aria-label="PureGamma 系统状态预览">
          <div className="terminalTop"><span>PG / SYSTEM STATUS</span><span className="live">● LIVE</span></div>
          <div className="marketLine"><span>RESEARCH ENGINE</span><strong>ONLINE</strong></div>
          <div className="metric"><span className="metricLabel">CONTROL PLANE</span><b>04</b><small>guardrails active</small></div>
          <div className="chart" aria-hidden="true"><i /><i /><i /><i /><i /><i /><i /><i /><i /><i /><i /><i /></div>
          <div className="terminalGrid">
            <div><small>EXECUTION</small><strong>PAPER</strong></div>
            <div><small>DATABASE</small><strong>MIGRATED</strong></div>
            <div><small>RISK MODE</small><strong>STRICT</strong></div>
          </div>
        </div>
      </section>

      <section className="ticker" aria-label="核心特性">
        <div>RESEARCH WITH SOURCES <span>◆</span> PORTFOLIO MONITORING <span>◆</span> CONTROLLED AUTOMATION <span>◆</span> BILINGUAL WORKSPACE <span>◆</span> PAPER-FIRST EXECUTION</div>
      </section>

      <section id="system" className="section shell">
        <div className="sectionHead"><span>01 / THE SYSTEM</span><h2>从信息噪声到可执行判断</h2><p>不是另一个聊天窗口，而是一套把数据、推理、权限和操作串在一起的工作流。</p></div>
        <div className="cards">
          {capabilities.map(([n, title, body]) => <article className="card" key={n}><span>{n}</span><h3>{title}</h3><p>{body}</p><div className="cardLine" /></article>)}
        </div>
      </section>

      <section className="control shell">
        <div><span className="label">DESIGNED FOR CONTROL</span><h2>自动化可以更快，<br />权限必须更慢。</h2></div>
        <div className="controlList">
          <p><b>01</b><span><strong>默认安全</strong>实盘、转账与提现能力默认关闭。</span></p>
          <p><b>02</b><span><strong>全程可追溯</strong>研究来源、任务运行与关键操作保留记录。</span></p>
          <p><b>03</b><span><strong>按层开放</strong>研究、组合、模拟与执行能力独立授权。</span></p>
        </div>
      </section>

      <section id="release" className="section shell release">
        <div className="sectionHead"><span>02 / RELEASE READINESS</span><h2>第一版，诚实地展示边界</h2></div>
        <div className="releaseTable">
          {release.map(([area, item, state]) => <div key={area}><code>{area}</code><span>{item}</span><strong className={state === "READY" ? "ready" : "pending"}>{state}</strong></div>)}
        </div>
        <p className="releaseNote">产品核心栈已通过容器化启动与健康检查。正式用户开放仍以域名、支付与身份服务完成生产配置为准。</p>
      </section>

      <section className="cta shell"><span className="label">PUREGAMMA AI / PRIVATE PREVIEW</span><h2>让复杂市场工作，<br />变得清晰、连续、可控。</h2><a className="button light" href="mailto:hello@puregamma.ai?subject=PureGamma%20AI%20首批访问">申请首批访问 <span>↗</span></a></section>

      <footer className="footer shell"><div className="brand"><span className="brandMark">PΓ</span><span>PureGamma AI</span></div><p>AI research, portfolio intelligence and controlled execution.</p><small>© 2026 PureGamma AI · Private preview · Not investment advice</small></footer>
    </main>
  );
}
