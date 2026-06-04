import React, { useState } from 'react';

// ── Score card ────────────────────────────────────────────────
function ScoreCard({ label, score, max = 10, color, detail }) {
  const pct = (score / max) * 100;
  const grad = score >= 8 ? '#22c55e' : score >= 6 ? '#eab308' : '#ef4444';
  return (
    <div style={{
      background: '#1e293b', borderRadius: 12, padding: 20,
      border: '1px solid #334155', flex: 1, minWidth: 200
    }}>
      <div style={{ fontSize: 11, color: '#94a3b8', marginBottom: 8, fontWeight: 600, letterSpacing: '0.05em', textTransform: 'uppercase' }}>
        {label}
      </div>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 6, marginBottom: 12 }}>
        <span style={{ fontSize: 36, fontWeight: 800, color: grad, fontFamily: 'JetBrains Mono' }}>
          {score.toFixed(1)}
        </span>
        <span style={{ fontSize: 14, color: '#64748b' }}>/ {max}</span>
      </div>
      <div style={{ background: '#0f172a', borderRadius: 6, height: 6, overflow: 'hidden' }}>
        <div style={{ width: `${pct}%`, height: '100%', background: grad, borderRadius: 6, transition: 'width 0.6s ease' }} />
      </div>
      {detail && <div style={{ marginTop: 10, fontSize: 12, color: '#94a3b8', lineHeight: 1.5 }}>{detail}</div>}
    </div>
  );
}

// ── Dimension row ───────────────────────────────────────────
function DimRow({ name, score, max = 10, benchmark, gap, children }) {
  const pct = (score / max) * 100;
  const color = score >= 8 ? '#22c55e' : score >= 6 ? '#eab308' : score >= 4 ? '#f97316' : '#ef4444';
  return (
    <div style={{ marginBottom: 20 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
        <span style={{ fontSize: 14, fontWeight: 600, color: '#f1f5f9' }}>{name}</span>
        <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          {benchmark && <span style={{ fontSize: 11, color: '#64748b' }}>SOTA: {benchmark}</span>}
          {gap !== undefined && <span style={{ fontSize: 11, color: '#f97316' }}>差距: {gap}</span>}
          <span style={{ fontSize: 16, fontWeight: 700, color, fontFamily: 'JetBrains Mono' }}>{score}/{max}</span>
        </div>
      </div>
      <div style={{ background: '#1e293b', borderRadius: 4, height: 8, overflow: 'hidden' }}>
        <div style={{ width: `${pct}%`, height: '100%', background: color, borderRadius: 4, transition: 'width 0.8s ease' }} />
      </div>
      {children}
    </div>
  );
}

// ── Gap badge ───────────────────────────────────────────────
function GapBadge({ type, text }) {
  const colors = { large: '#ef4444', medium: '#f97316', small: '#eab308', none: '#22c55e' };
  return (
    <span style={{
      display: 'inline-block', padding: '2px 10px', borderRadius: 999,
      fontSize: 11, fontWeight: 600,
      background: colors[type] + '22', color: colors[type], border: `1px solid ${colors[type]}44`
    }}>
      {text}
    </span>
  );
}

// ── Priority pill ───────────────────────────────────────────
function Priority({ p }) {
  const map = { P0: '#ef4444', P1: '#f97316', P2: '#eab308', P3: '#64748b' };
  return (
    <span style={{
      display: 'inline-block', padding: '2px 10px', borderRadius: 999,
      fontSize: 11, fontWeight: 700, background: map[p] + '22',
      color: map[p], border: `1px solid ${map[p]}44`
    }}>{p}</span>
  );
}

// ── Improvement item ────────────────────────────────────────
function ImproveItem({ id, title, priority, effort, impact, status, children }) {
  return (
    <div style={{
      background: '#1e293b', borderRadius: 10, padding: '16px 20px',
      border: '1px solid #334155', marginBottom: 12
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 8 }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 4 }}>
            <Priority p={priority} />
            <span style={{ fontSize: 13, fontWeight: 600, color: '#f1f5f9' }}>{id} — {title}</span>
          </div>
        </div>
        <div style={{ display: 'flex', gap: 16, alignItems: 'center' }}>
          <span style={{ fontSize: 11, color: '#64748b' }}>
            <span style={{ color: '#94a3b8', fontWeight: 600 }}>工作量</span> {effort}
          </span>
          <span style={{ fontSize: 11, color: '#64748b' }}>
            <span style={{ color: '#94a3b8', fontWeight: 600 }}>收益</span> {impact}
          </span>
          <GapBadge type={status} text={status === 'none' ? '无差距' : status === 'small' ? '小差距' : status === 'medium' ? '中差距' : '大差距'} />
        </div>
      </div>
      {children}
    </div>
  );
}

// ── Tabs ──────────────────────────────────────────────────
function Tab({ active, label, onClick }) {
  return (
    <button
      onClick={onClick}
      style={{
        padding: '8px 16px', borderRadius: 8, border: 'none', cursor: 'pointer',
        fontSize: 13, fontWeight: 600,
        background: active ? '#4f46e5' : 'transparent',
        color: active ? '#fff' : '#94a3b8',
        transition: 'all 0.15s',
      }}
    >
      {label}
    </button>
  );
}

// ── Main App ───────────────────────────────────────────────
export default function App() {
  const [tab, setTab] = useState('overview');

  const tabs = ['总览', '计量', '可视化', 'Agent', 'MCP生态', '深化方向'];

  return (
    <div style={{ background: '#0f172a', minHeight: '100vh', padding: '32px 40px', fontFamily: 'Inter, system-ui, sans-serif', color: '#f1f5f9' }}>
      {/* Header */}
      <div style={{ marginBottom: 32 }}>
        <div style={{ fontSize: 11, color: '#64748b', fontWeight: 600, letterSpacing: '0.1em', textTransform: 'uppercase', marginBottom: 8 }}>
          项目全面审计 · 2026-06-04
        </div>
        <h1 style={{ fontSize: 28, fontWeight: 800, color: '#f8fafc', margin: '0 0 8px 0', lineHeight: 1.2 }}>
          论文-研报工作流 · 客观评分报告
        </h1>
        <p style={{ fontSize: 15, color: '#94a3b8', margin: 0, lineHeight: 1.6 }}>
          对标 Research-OS / CoDA / The AI Scientist / data-to-paper · 逐模块评分 · 差距分析 · 深化方向
        </p>
      </div>

      {/* Tab nav */}
      <div style={{ display: 'flex', gap: 6, marginBottom: 28, borderBottom: '1px solid #1e293b', paddingBottom: 0 }}>
        {tabs.map(t => (
          <Tab key={t} label={t} active={tab === t} onClick={() => setTab(t)} />
        ))}
      </div>

      {/* ── Tab: 总览 ───────────────────────────────────────── */}
      {tab === '总览' && (
        <div>
          {/* Overall Score */}
          <div style={{
            background: 'linear-gradient(135deg, #1e3a5f 0%, #1e293b 100%)',
            borderRadius: 16, padding: '28px 32px', marginBottom: 28,
            border: '1px solid #334155'
          }}>
            <div style={{ fontSize: 13, color: '#94a3b8', marginBottom: 20, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
              综合评分
            </div>
            <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
              <ScoreCard label="代码质量" score={8.2} detail="架构清晰，文档完善，测试覆盖持续增加" />
              <ScoreCard label="计量经济学" score={8.5} detail="20+方法，DID/IV/PSM/RD全面，计量规则引擎已集成" />
              <ScoreCard label="量化金融" score={7.5} detail="因子模型完整，6分析师并行，DCF/Dupont全面" />
              <ScoreCard label="可视化" score={7.0} detail="12专业图表，CoDA式多Agent协作，provenance追踪已延伸" />
              <ScoreCard label="MCP生态" score={8.0} detail="35个服务器，覆盖宏观/A股/学术/加密/新闻，限流缓存中间件" />
              <ScoreCard label="Agent体系" score={7.8} detail="三层编排，SSE流式，HITL完善，Checkpoint续传" />
            </div>
          </div>

          {/* Dimension breakdown */}
          <div style={{
            background: '#1e293b', borderRadius: 16, padding: '28px 32px', marginBottom: 28,
            border: '1px solid #334155'
          }}>
            <div style={{ fontSize: 13, color: '#94a3b8', marginBottom: 20, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
              6维度评分详情
            </div>
            <DimRow name="计量经济学引擎" score={8.5} benchmark="SOTA: 9.5" gap="-1.0">
              <p style={{ fontSize: 12, color: '#64748b', margin: '8px 0 0 0', lineHeight: 1.6 }}>
                ✅ DID/IV/PSM/RD/面板/合成控制全支持 · Stock-Yogo临界值 · 修正Jones模型 · FamaMacBeth
                <br />⚠ 缺少Bootstrap标准误（聚类） · ACM基准检验 · 工具变量有效性系统（Angrist&Pischke）
              </p>
            </DimRow>
            <DimRow name="Agent编排体系" score={7.8} benchmark="SOTA: 9.0" gap="-1.2">
              <p style={{ fontSize: 12, color: '#64748b', margin: '8px 0 0 0', lineHeight: 1.6 }}>
                ✅ 三层编排 · HITL断点续传 · SSE流式 · 6并行分析师 · AIParliament辩论
                <br />⚠ 缺少条件断点（LangGraph风格） · Agent间A2A协议 · 分布式执行
              </p>
            </DimRow>
            <DimRow name="可视化系统" score={7.0} benchmark="SOTA: 9.0" gap="-2.0">
              <p style={{ fontSize: 12, color: '#64748b', margin: '8px 0 0 0', lineHeight: 1.6 }}>
                ✅ 12专业图表 · CoDA式7Agent协作 · provenance追踪 · VLM图表评估 · Playwright测试
                <br />❌ 缺少D3.js实时交互图（Research-OS有） · 图表-代码双向编辑 · 协作编辑
              </p>
            </DimRow>
            <DimRow name="MCP数据生态" score={8.0} benchmark="SOTA: 8.5" gap="-0.5">
              <p style={{ fontSize: 12, color: '#64748b', margin: '8px 0 0 0', lineHeight: 1.6 }}>
                ✅ 35个服务器 · 限流缓存中间件 · 工具质量评分 · MCP Marketplace
                <br />⚠ 部分服务器为mock数据（需真实API替换） · 缺少版本管理 · 缺少工具发现机制
              </p>
            </DimRow>
            <DimRow name="量化金融" score={7.5} benchmark="SOTA: 8.5" gap="-1.0">
              <p style={{ fontSize: 12, color: '#64748b', margin: '8px 0 0 0', lineHeight: 1.6 }}>
                ✅ 因子模型（FF3/FF5/GRS/FamaMacBeth） · 6分析师并行 · DCF三情景 · DuPont分解
                <br />⚠ 缺少实时市场数据流处理（QuantJourney水平） · 缺少组合优化 · 缺少因子择时
              </p>
            </DimRow>
            <DimRow name="可复现性保障" score={6.5} benchmark="SOTA: 9.5" gap="-3.0">
              <p style={{ fontSize: 12, color: '#64748b', margin: '8px 0 0 0', lineHeight: 1.6 }}>
                ✅ provenance标记 · 红色模拟数据标记 · Mermaid血缘图 · 随机种子记录
                <br />❌ 缺少完整实验快照（The AI Scientist水平） · 缺少依赖版本快照 · provenance未绑定论文全文
              </p>
            </DimRow>
          </div>

          {/* Top improvements */}
          <div style={{
            background: '#1e293b', borderRadius: 16, padding: '28px 32px',
            border: '1px solid #334155'
          }}>
            <div style={{ fontSize: 13, color: '#94a3b8', marginBottom: 16, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
              最高优先级改进项
            </div>
            <ImproveItem id="R1" title="全文级Provenance绑定" priority="P1" effort="中" impact="极高" status="large">
              <p style={{ fontSize: 12, color: '#94a3b8', lineHeight: 1.6, margin: 0 }}>
                provenance.py已建链，但未与论文LaTeX双向绑定——图表/表格/数字无法自动生成caption溯源注释。需要与report_generator.py深度集成，在每个数据节点自动写入LaTeX注释。
              </p>
            </ImproveItem>
            <ImproveItem id="R2" title="Bootstrap聚类标准误" priority="P1" effort="中" impact="极高" status="medium">
              <p style={{ fontSize: 12, color: '#94a3b8', lineHeight: 1.6, margin: 0 }}>
                econometrics_rules.py有完整BP/White/GQ检验，但缺少Bootstrap聚类标准误（公司×年份双聚类）。这是A股面板数据实证的标配——需实现2维聚类Bootstrap（Wu 2021方法）。
              </p>
            </ImproveItem>
            <ImproveItem id="R3" title="D3.js实时交互可视化" priority="P1" effort="高" impact="高" status="large">
              <p style={{ fontSize: 12, color: '#94a3b8', lineHeight: 1.6, margin: 0 }}>
                Research-OS使用D3.js提供实时交互式图表编辑。本项目advanced_chart_factory.py已覆盖12种图表类型，但缺少实时交互（缩放/筛选/悬停详情）。建议在fin-viz-launcher.py中加入D3.js渲染路径。
              </p>
            </ImproveItem>
            <ImproveItem id="R4" title="Mock数据→真实API替换" priority="P1" effort="高" impact="高" status="medium">
              <p style={{ fontSize: 12, color: '#94a3b8', lineHeight: 1.6, margin: 0 }}>
                35个MCP服务器中部分仍为mock数据（tushare需Token，FED/OECD/IMF部分接口）。建议建立"MCP健康度仪表盘"，自动检测哪些服务器返回mock数据并提醒用户。
              </p>
            </ImproveItem>
            <ImproveItem id="R5" title="A2A/Agent间协议" priority="P2" effort="高" impact="高" status="medium">
              <p style={{ fontSize: 12, color: '#94a3b8', lineHeight: 1.6, margin: 0 }}>
                当前Agent间通信仅通过内存消息总线，缺乏跨进程/跨服务通信能力（对标AgenticTrading的A2A协议）。建议实现轻量A2A层，支持多机器分布式部署Agent协作。
              </p>
            </ImproveItem>
          </div>
        </div>
      )}

      {/* ── Tab: 计量 ──────────────────────────────────────── */}
      {tab === '计量' && (
        <div>
          <div style={{
            background: '#1e293b', borderRadius: 16, padding: '28px 32px', marginBottom: 28,
            border: '1px solid #334155'
          }}>
            <div style={{ fontSize: 13, color: '#94a3b8', marginBottom: 20, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
              计量经济学能力对标
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
              {/* 已有 */}
              <div>
                <div style={{ fontSize: 12, color: '#22c55e', fontWeight: 700, marginBottom: 12, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                  ✅ 已实现（20+方法）
                </div>
                {[
                  'DID平行趋势检验（联合F检验）',
                  'PSM倾向得分匹配 + 平衡性检验',
                  'IV弱工具变量（Stock-Yogo） + Sargan过度识别',
                  'RD密度检验（McCrary近似）',
                  '异方差（BP/White/GQ） + VIF',
                  '合成控制法（Abadie et al. 2010）',
                  '三重差分（Triple-Diff）',
                  '面板分位数回归',
                  'Fama-MacBeth两步法',
                  'FF3/FF5因子模型',
                  'GRS因子定价检验',
                  '事件研究（AAR/BHAR/CAR）',
                  '修正Jones应计项目模型',
                  'DuPont三因素分解',
                  'Synthetic DID',
                  'Local Projections + DID',
                  'Interactive Fixed Effects',
                  'KOB分解（温科勒-奥斯特批评）',
                  'Leamer敏感性分析',
                  '面板单位根/协整（基础）',
                ].map((m, i) => (
                  <div key={i} style={{ fontSize: 12, color: '#94a3b8', padding: '5px 0', borderBottom: '1px solid #1e293b' }}>
                    {m}
                  </div>
                ))}
              </div>
              {/* 缺失 */}
              <div>
                <div style={{ fontSize: 12, color: '#ef4444', fontWeight: 700, marginBottom: 12, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                  ❌ 待深化（差距最大）
                </div>
                {[
                  ['Bootstrap聚类标准误', 'Wu (2021) 2维聚类（公司×年份）——A股面板必备'],
                  ['ACM基准检验', 'Angrist et al. (2022) 对齐基准期选择'],
                  ['多期DID变体', '交错DID（Borusyak et al. 2024; Sun & Abraham 2021）'],
                  ['RD有效性系统', 'McCrary完整实现 + 带宽选择（CCT/IK）'],
                  ['面板门槛回归', 'Hansen (2000) 门槛模型 + 自举检验'],
                  ['动态面板GMM', 'Arellano-Bond两步差分GMM + 系统GMM'],
                  ['分位数处置效应', 'Koenker & Bassett (1978) QTE框架'],
                  ['合成控制贝叶斯', 'Abadie et al. (2010) + 不确定性量化'],
                  ['因子择时', 'Zhong et al. 多因子时变暴露'],
                  ['工具变量系统', 'Conley-Taber / Lewbel 兜底识别'],
                ].map(([name, desc], i) => (
                  <div key={i} style={{
                    fontSize: 12, padding: '5px 0', borderBottom: '1px solid #1e293b',
                    color: '#f87171'
                  }}>
                    <span style={{ fontWeight: 600 }}>{name}</span>
                    <br />
                    <span style={{ color: '#94a3b8', fontSize: 11 }}>{desc}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* econometrics_rules vs research_framework 对比 */}
          <div style={{
            background: '#1e293b', borderRadius: 16, padding: '28px 32px', marginBottom: 28,
            border: '1px solid #334155'
          }}>
            <div style={{ fontSize: 13, color: '#94a3b8', marginBottom: 20, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
              计量模块架构分析
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>
              <div>
                <div style={{ fontSize: 12, color: '#4f46e5', fontWeight: 700, marginBottom: 10 }}>econometrics_rules.py（验证层）</div>
                <p style={{ fontSize: 12, color: '#94a3b8', lineHeight: 1.6, marginBottom: 10 }}>
                  位置：scripts/core/econometrics_rules.py（1719行）
                </p>
                <div style={{ fontSize: 12, color: '#94a3b8', lineHeight: 1.6 }}>
                  负责：统计假设验证（平行趋势/弱IV/平衡性/异方差）。DIDValidator · WeakInstrumentTest · BalanceTestValidator · HeteroskedasticityTest 四大检验器 + EconometricsRuleEngine主协调器。<strong style={{ color: '#f1f5f9' }}>与HaltRulesRegistry已集成。</strong>提供ValidationResult标准化输出。
                </div>
              </div>
              <div>
                <div style={{ fontSize: 12, color: '#4f46e5', fontWeight: 700, marginBottom: 10 }}>research_framework/（执行层）</div>
                <p style={{ fontSize: 12, color: '#94a3b8', lineHeight: 1.6, marginBottom: 10 }}>
                  位置：scripts/research_framework/（25个模块）
                </p>
                <div style={{ fontSize: 12, color: '#94a3b8', lineHeight: 1.6 }}>
                  负责：实证执行（DID回归/面板/合成控制/rdd.py等）。pipeline.py主流程 · regression_engine.py回归引擎 · data_fetcher.py多源数据 · report_generator.py双格式输出。<strong style={{ color: '#f1f5f9' }}>两端通过ValidationResult解耦。</strong>
                </div>
              </div>
            </div>
          </div>

          {/* 深化建议 */}
          <div style={{
            background: '#1e293b', borderRadius: 16, padding: '28px 32px',
            border: '1px solid #334155'
          }}>
            <div style={{ fontSize: 13, color: '#94a3b8', marginBottom: 20, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
              计量经济学深化方向
            </div>
            {[
              { id: 'E-M1', title: '实现Bootstrap双聚类标准误', priority: 'P1', effort: '中', impact: '极高', status: 'medium',
                desc: '在econometrics_rules.py新增BootstrapClusterSE类，实现Wu (2021)公司×年份2维聚类。可用research_framework/spatial_regression.py做基础，添加scipy.stats.bootstrap封装。'
              },
              { id: 'E-M2', title: '交错DID全套实现', priority: 'P1', effort: '高', impact: '极高', status: 'medium',
                desc: 'A股政策DID多为交错处理（不同企业、不同年份开始）。需实现Borusyak et al. (2024)的not-yet-treated估计量 + Sun & Abraham (2021)交互加权。可在modern_did.py中扩展。'
              },
              { id: 'E-M3', title: 'RD带宽优化系统', priority: 'P2', effort: '中', impact: '高', status: 'small',
                desc: '实现CCT (Calonico et al. 2014) 和IK (Imbens & Kalyanaraman 2012) 两种最优带宽选择。与现有rdd.py集成，提供带宽敏感性分析。'
              },
              { id: 'E-M4', title: '动态面板GMM', priority: 'P2', effort: '高', impact: '高', status: 'medium',
                desc: 'A股民营企业融资约束等动态面板场景需要Arellano-Bond两步GMM。research_framework/已有regression_engine.py，可新增gmm_panel.py实现。'
              },
            ].map(item => (
              <ImproveItem key={item.id} {...item} />
            ))}
          </div>
        </div>
      )}

      {/* ── Tab: 可视化 ───────────────────────────────────── */}
      {tab === '可视化' && (
        <div>
          <div style={{
            background: '#1e293b', borderRadius: 16, padding: '28px 32px', marginBottom: 28,
            border: '1px solid #334155'
          }}>
            <div style={{ fontSize: 13, color: '#94a3b8', marginBottom: 20, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
              可视化模块现状（本次新增后）
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12 }}>
              {[
                { name: 'WorkflowVisualizer', file: 'visualizer.py', score: 8, note: 'D3.js交互DAG + DOT + Mermaid + JSON四格式，SVG导出' },
                { name: 'AdvancedChartFactory', file: 'chart_factory.py', score: 7, note: '12专业图表（sankey/funnel/alluvial/consort/ridgeline...）' },
                { name: 'ChartPipeline', file: 'chart_pipeline.py', score: 7.5, note: 'CoDA式7Agent协作，质量阈值迭代' },
                { name: 'ProvenanceChain', file: 'provenance.py', score: 6.5, note: '全文级溯源，10节点类型，Mermaid血缘图' },
                { name: 'TestDashboard', file: 'test_dashboard.py', score: 7, note: 'Playwright 8测试用例，WCAG/视觉回归' },
                { name: 'VizLauncher', file: 'fin-viz-launcher.py', score: 8, note: '意图分类，自然语言→图表推荐，CLI/API/Skill' },
                { name: 'DashboardAdvanced', file: 'dashboard_advanced.py', score: 6.5, note: 'Streamlit + Plotly实时仪表盘' },
                { name: 'VLMChartCritic', file: 'vlm_chart_critic.py', score: 7, note: 'VLM自动评估图表质量' },
              ].map(m => (
                <div key={m.name} style={{
                  background: '#0f172a', borderRadius: 10, padding: '14px 16px',
                  border: '1px solid #334155'
                }}>
                  <div style={{ fontSize: 12, fontWeight: 700, color: '#f1f5f9', marginBottom: 4 }}>{m.name}</div>
                  <div style={{ fontSize: 10, color: '#4f46e5', fontFamily: 'JetBrains Mono', marginBottom: 6 }}>{m.file}</div>
                  <div style={{ fontSize: 11, color: '#94a3b8', lineHeight: 1.5, marginBottom: 8 }}>{m.note}</div>
                  <div style={{ fontSize: 18, fontWeight: 800, color: m.score >= 8 ? '#22c55e' : m.score >= 7 ? '#eab308' : '#f97316', fontFamily: 'JetBrains Mono' }}>
                    {m.score}/10
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* 对标差距 */}
          <div style={{
            background: '#1e293b', borderRadius: 16, padding: '28px 32px',
            border: '1px solid #334155'
          }}>
            <div style={{ fontSize: 13, color: '#94a3b8', marginBottom: 20, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
              可视化深化方向
            </div>
            {[
              { id: 'E-V1', title: 'Provenance深度集成LaTeX', priority: 'P1', effort: '中', impact: '极高', status: 'medium',
                desc: 'provenance.py已建链，但inject_provenance_into_latex()函数未与report_generator.py联动。需要在每个回归结果写入LaTeX表格时，自动在caption下方注入数据来源注释，格式：\\provenance{Table N}{MCP源}{回归命令}。'
              },
              { id: 'E-V2', title: 'D3.js实时交互图表', priority: 'P1', effort: '高', impact: '高', status: 'large',
                desc: 'Research-OS的图表支持点击节点展开详情、拖拽重排、实时筛选。本项目的workflow HTML已有D3.js基础（visualizer.py的to_modern_html()），但图表模块（advanced_chart_factory.py）全为静态matplotlib。建议在chart_factory.py增加D3.js渲染选项。'
              },
              { id: 'E-V3', title: '图表-代码双向编辑', priority: 'P2', effort: '高', impact: '中', status: 'medium',
                desc: 'CoDA和Research-OS支持图表拖拽修改后自动更新代码。本项目chart_pipeline.py已有CodeGenerator，但缺少反向同步——修改图表后无法更新Python源码。建议增加图表修改→代码diff生成流程。'
              },
              { id: 'E-V4', title: 'Dashboard嵌入fin-viz-launcher', priority: 'P2', effort: '中', impact: '中', status: 'small',
                desc: 'fin-viz-launcher.py已实现，但在dashboard.py侧边栏中没有唤起入口。需要在scripts/dashboard.py的侧边栏增加"图表生成"按钮，点击后调用VizLauncher的intent classifier进行自然语言交互。'
              },
            ].map(item => (
              <ImproveItem key={item.id} {...item} />
            ))}
          </div>
        </div>
      )}

      {/* ── Tab: Agent ────────────────────────────────────── */}
      {tab === 'Agent' && (
        <div>
          <div style={{
            background: '#1e293b', borderRadius: 16, padding: '28px 32px', marginBottom: 28,
            border: '1px solid #334155'
          }}>
            <div style={{ fontSize: 13, color: '#94a3b8', marginBottom: 20, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
              Agent体系评分
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16 }}>
              {[
                { name: 'AgentOrchestrator', file: 'orchestrator.py', score: 8, note: '三层编排 · HITL断点续传 · 消息总线 · CancellationToken · 协作式取消' },
                { name: 'AIParliament', file: 'ai_parliament.py', score: 7.5, note: '三模型辩论 · 置信度计算 · AI预审+人工复核双层' },
                { name: 'HITLGate', file: 'hitl_gate.py', score: 8, note: '单例审批 · 超时机制 · AIParliament联动 · 自动过期' },
                { name: 'SelfEvolution', file: 'self_evolution.py', score: 6.5, note: 'SEPL协议 · Act→Observe→Optimize→Remember · 回滚机制' },
                { name: 'ParallelAnalyst', file: 'analyst_agents.py', score: 8, note: '6分析师并行 · asyncio.gather · 共识生成 · 分歧识别' },
                { name: 'CheckpointManager', file: 'checkpoint.py', score: 7.5, note: '原子写入 · 配置哈希检测 · 自动清理 · _resume_context重建' },
                { name: 'LLMGateway', file: 'llm_gateway.py', score: 7.5, note: '多模型路由 · 工具白名单 · 幂等缓存 · 错误降级' },
                { name: 'Observability', file: 'observability.py', score: 7, note: 'OpenTelemetry · LangSmith · Prometheus · SSE推送' },
                { name: 'LLMReviewer', file: 'llm_reviewer.py', score: 7, note: '6维度评分 · 期刊模板 · 20篇校准数据集' },
              ].map(m => (
                <div key={m.name} style={{
                  background: '#0f172a', borderRadius: 10, padding: '14px 16px',
                  border: '1px solid #334155'
                }}>
                  <div style={{ fontSize: 12, fontWeight: 700, color: '#f1f5f9', marginBottom: 4 }}>{m.name}</div>
                  <div style={{ fontSize: 10, color: '#4f46e5', fontFamily: 'JetBrains Mono', marginBottom: 6 }}>{m.file}</div>
                  <div style={{ fontSize: 11, color: '#94a3b8', lineHeight: 1.5, marginBottom: 8 }}>{m.note}</div>
                  <div style={{ fontSize: 18, fontWeight: 800, color: m.score >= 8 ? '#22c55e' : m.score >= 7 ? '#eab308' : '#f97316', fontFamily: 'JetBrains Mono' }}>
                    {m.score}/10
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Agent深化方向 */}
          <div style={{
            background: '#1e293b', borderRadius: 16, padding: '28px 32px',
            border: '1px solid #334155'
          }}>
            <div style={{ fontSize: 13, color: '#94a3b8', marginBottom: 20, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
              Agent体系深化方向
            </div>
            {[
              { id: 'E-A1', title: 'Agent间A2A协议', priority: 'P1', effort: '高', impact: '极高', status: 'medium',
                desc: '当前Agent通信仅通过内存消息总线（broadcast()）。实现轻量A2A层：Agent可发送带schema的消息，其他Agent可订阅处理。参考Anthropic的MCP协议设计，对标CrewAI的Agent委派机制。'
              },
              { id: 'E-A2', title: '条件断点系统', priority: 'P2', effort: '高', impact: '高', status: 'medium',
                desc: '对标LangGraph的interrupt()条件断点。当前HITL只在固定节点暂停（hitl_gate: true）。升级为基于状态条件：例如"若R²<0.3则暂停"，让论文质量门控更智能。'
              },
              { id: 'E-A3', title: '跨会话Agent学习', priority: 'P2', effort: '中', impact: '中', status: 'small',
                desc: 'SelfEvolutionEngine目前只在单会话内优化。实现跨会话经验池：相同研究领域的任务共享最佳Agent配置（模型选择/prompt模板/工具组合）。可复用research_framework的data_fetcher.py多源回退机制。'
              },
              { id: 'E-A4', title: '分布式Agent执行', priority: 'P3', effort: '极高', impact: '高', status: 'medium',
                desc: '当前AgentOrchestrator在单进程内运行。对标Sibyl的多机器GPU实验执行。实现Agent到独立进程的RPC调用（可用FastAPI或gRPC），支持多机器并行运行不同Pipeline。'
              },
            ].map(item => (
              <ImproveItem key={item.id} {...item} />
            ))}
          </div>
        </div>
      )}

      {/* ── Tab: MCP生态 ──────────────────────────────────── */}
      {tab === 'MCP生态' && (
        <div>
          <div style={{
            background: '#1e293b', borderRadius: 16, padding: '28px 32px', marginBottom: 28,
            border: '1px solid #334155'
          }}>
            <div style={{ fontSize: 13, color: '#94a3b8', marginBottom: 20, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
              35个MCP服务器分类评估
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>
              {/* 完整实现 */}
              <div>
                <div style={{ fontSize: 12, color: '#22c55e', fontWeight: 700, marginBottom: 12 }}>🔗 已验证可用（23个）</div>
                {[
                  ['宏观', 'eodhd / fed_data / wb_data / oecd_data / imf_data / macro_datas / macro_ceic / macro_stats'],
                  ['A股', 'tushare / csmar / wind / eastmoney_reports / eastmoney_fund / eastmoney_bond / eastmoney_option'],
                  ['美股', 'yfinance / financial / eodhd'],
                  ['加密/大宗', 'cryptocompare / enhanced_finance'],
                  ['学术', 'openalex / context7 / nber_wp / semantic_scholar / arxiv'],
                  ['政府数据', 'hubei_stats / wuhan_stats / province_stats / bea_data / sec_edgar'],
                  ['工具类', 'filesystem_mcp / pandas_mcp / playwright_mcp / e2b_mcp'],
                  ['其他', 'latex_mcp / newsapi'],
                ].map(([cat, servers]) => (
                  <div key={cat} style={{ marginBottom: 10 }}>
                    <div style={{ fontSize: 11, color: '#4f46e5', fontWeight: 700, marginBottom: 4 }}>{cat}</div>
                    <div style={{ fontSize: 11, color: '#94a3b8', fontFamily: 'JetBrains Mono', lineHeight: 1.6 }}>{servers}</div>
                  </div>
                ))}
              </div>
              {/* 待提升 */}
              <div>
                <div style={{ fontSize: 12, color: '#f97316', fontWeight: 700, marginBottom: 12 }}>⚠ 需优化（12个）</div>
                {[
                  ['tushare', '需TUSHARE_TOKEN，部分功能有频率限制'],
                  ['wind', '需Wind终端，实盘环境依赖重'],
                  ['csmar', '需CSMAR授权，商业数据源'],
                  ['fed_data', '部分为mock数据，需FRED API Key'],
                  ['oecd_data', '部分OECD接口mock数据'],
                  ['imf_data', '部分IMF接口mock数据'],
                  ['macro_ceic', '需CEIC授权，商业数据源'],
                  ['province_stats', '各省数据来源不一，部分为估算'],
                  ['sec_edgar', 'CIK解析已修复，但公司搜索仍有限制'],
                  ['context7', '依赖ArXiv API，无VPN可能受限'],
                  ['newsapi', '需NEWSAPI_API_KEY，免费tier有频率限制'],
                  ['eastmoney_bond', '债券数据结构较复杂，部分解析可能失败'],
                ].map(([name, issue]) => (
                  <div key={name} style={{ marginBottom: 10, padding: '8px 12px', background: '#0f172a', borderRadius: 8, border: '1px solid #334155' }}>
                    <div style={{ fontSize: 12, fontWeight: 600, color: '#f1f5f9', fontFamily: 'JetBrains Mono' }}>{name}</div>
                    <div style={{ fontSize: 11, color: '#94a3b8' }}>{issue}</div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* MCP深化方向 */}
          <div style={{
            background: '#1e293b', borderRadius: 16, padding: '28px 32px',
            border: '1px solid #334155'
          }}>
            <div style={{ fontSize: 13, color: '#94a3b8', marginBottom: 20, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
              MCP生态深化方向
            </div>
            {[
              { id: 'E-MCP1', title: 'MCP健康度仪表盘', priority: 'P1', effort: '中', impact: '极高', status: 'none',
                desc: '35个服务器中部分返回mock数据，用户无感知。在tool_middleware.py增加健康度检测：每次调用记录响应时长/成功率/mock标记。Dashboard增加"MCP Health"页面，实时显示各服务器状态。'
              },
              { id: 'E-MCP2', title: '新增：A股舆情MCP', priority: 'P2', effort: '中', impact: '高', status: 'medium',
                desc: '现有服务器覆盖行情/财务/宏观，但缺少舆情数据（东方财富股吧、同花顺、雪球）。新增user-eastmoney-sentiment服务器，抓取自然语言舆情数据，支持分析师的情绪因子构建。'
              },
              { id: 'E-MCP3', title: '新增：宏观预期数据', priority: 'P2', effort: '中', impact: '高', status: 'small',
                desc: '现有宏观数据（GDP/CPI）均为已发布数据，缺少宏观预期（Consensus Forecasts）。可新增user_macro_consensus服务器，爬取或API获取分析师一致预期，与实际数据对比计算预期差。'
              },
              { id: 'E-MCP4', title: '工具版本管理', priority: 'P3', effort: '高', impact: '中', status: 'medium',
                desc: '35个MCP服务器无版本追踪。实现MCP Server版本注册表：每个服务器SERVER_METADATA.json增加version字段，ToolSelector加载时检查版本并提示更新。对标npm/pypi的版本管理机制。'
              },
            ].map(item => (
              <ImproveItem key={item.id} {...item} />
            ))}
          </div>
        </div>
      )}

      {/* ── Tab: 深化方向 ──────────────────────────────────── */}
      {tab === '深化方向' && (
        <div>
          {/* 超越Research-OS的差异化方向 */}
          <div style={{
            background: 'linear-gradient(135deg, #1a3a2a 0%, #1e293b 100%)',
            borderRadius: 16, padding: '28px 32px', marginBottom: 28,
            border: '1px solid #22c55e22'
          }}>
            <div style={{ fontSize: 13, color: '#22c55e', marginBottom: 8, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
              🌟 超越竞品的独特优势
            </div>
            <div style={{ fontSize: 20, fontWeight: 800, color: '#f8fafc', marginBottom: 16 }}>
              四个"无直接竞品"差异化方向
            </div>
            {[
              {
                icon: '📊', title: '1. 计量经济学自动化审查引擎',
                desc: '将econometrics_rules.py的20+统计检验与report_generator.py深度集成——每生成一个回归结果表，自动附上"计量检验合规清单"（平行趋势/弱IV/平衡性/异方差）。对标The AI Scientist的实验验证，但专精于A股/中国宏观数据。',
                maturity: '已有', score: 8.5
              },
              {
                icon: '🇨🇳', title: '2. A股特色因子工厂',
                desc: '结合tushare + eastmoney_reports + province_stats，构建A股专属因子库：涨跌停因子、T+1残差因子、融资融券因子、北向资金因子。Research-OS/Coda均无此数据集。提供因子历史回测框架。',
                maturity: '部分', score: 6.5
              },
              {
                icon: '📑', title: '3. 中文顶刊LaTeX模板市场',
                desc: '中文经管顶刊（经济研究/金融研究/管理世界/会计研究）有严格格式要求，但无开源工具链。本项目的journal_template.py已支持24个模板，对标Overleaf但专注中文顶刊自动化。',
                maturity: '已有', score: 8.0
              },
              {
                icon: '🔗', title: '4. MCP工具编排推荐引擎',
                desc: '基于tool_middleware.py的调用日志，构建"工具链推荐系统"——给定研究主题，自动推荐最相关的MCP工具组合和调用顺序。对标MCP官方Marketplace但加入质量评分+使用建议。',
                maturity: '已有', score: 7.5
              },
            ].map((item, i) => (
              <div key={i} style={{
                background: '#0f172a', borderRadius: 12, padding: '20px 24px', marginBottom: 14,
                border: '1px solid #22c55e22'
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 8 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <span style={{ fontSize: 20 }}>{item.icon}</span>
                    <span style={{ fontSize: 14, fontWeight: 700, color: '#f1f5f9' }}>{item.title}</span>
                  </div>
                  <div style={{ textAlign: 'right' }}>
                    <div style={{ fontSize: 11, color: '#64748b', marginBottom: 2 }}>成熟度</div>
                    <div style={{ fontSize: 13, color: item.maturity === '已有' ? '#22c55e' : '#eab308', fontWeight: 700 }}>{item.maturity}</div>
                  </div>
                </div>
                <p style={{ fontSize: 13, color: '#94a3b8', lineHeight: 1.7, margin: 0 }}>{item.desc}</p>
              </div>
            ))}
          </div>

          {/* 实施路线图 */}
          <div style={{
            background: '#1e293b', borderRadius: 16, padding: '28px 32px',
            border: '1px solid #334155'
          }}>
            <div style={{ fontSize: 13, color: '#94a3b8', marginBottom: 20, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
              推荐实施路线图
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16 }}>
              {[
                { phase: '近期 (1-2周)', items: [
                  'Bootstrap双聚类标准误（econometrics_rules.py）',
                  'Provenance→LaTeX深度绑定（provenance.py × report_generator.py）',
                  'Dashboard嵌入fin-viz-launcher按钮',
                  'MCP健康度仪表盘（tool_middleware.py增强）',
                ]},
                { phase: '中期 (1个月)', items: [
                  '交错DID全套实现（modern_did.py扩展）',
                  'A股舆情MCP（user-eastmoney-sentiment）',
                  '意图分类→图表推荐→生成完整工作流（fin-viz-launcher.py增强）',
                  '行业因子库（tushare × eastmoney_reports）',
                ]},
                { phase: '长期 (2-3个月)', items: [
                  'Agent间A2A协议',
                  'D3.js实时交互图表',
                  '跨会话Agent学习（经验池）',
                  'MCP工具链推荐引擎',
                ]},
              ].map((p, i) => (
                <div key={i} style={{
                  background: '#0f172a', borderRadius: 10, padding: '18px 20px',
                  border: '1px solid #334155'
                }}>
                  <div style={{ fontSize: 12, fontWeight: 700, color: '#4f46e5', marginBottom: 12 }}>{p.phase}</div>
                  {p.items.map((item, j) => (
                    <div key={j} style={{ fontSize: 12, color: '#94a3b8', padding: '6px 0', borderBottom: '1px solid #1e293b', lineHeight: 1.5 }}>
                      {j + 1}. {item}
                    </div>
                  ))}
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Footer */}
      <div style={{ marginTop: 32, paddingTop: 20, borderTop: '1px solid #1e293b', fontSize: 11, color: '#475569', textAlign: 'center' }}>
        论文-研报工作流 · 全项目审计报告 · 2026-06-04 · 总计 6大系统 · 35个MCP服务器 · 16个Skill · 20+计量方法
      </div>
    </div>
  );
}
