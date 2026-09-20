import { useCallback, useEffect, useRef, useState } from 'react';
import { Alert, App as AntApp, Button, Checkbox, Empty, Input, Spin, Table, Tag, Upload } from 'antd';
import { ArrowUpOutlined, ArrowRightOutlined, BarChartOutlined, BookOutlined, CheckCircleFilled, DatabaseOutlined, FileExcelOutlined, HistoryOutlined, InboxOutlined, MessageOutlined, PlusOutlined, ReloadOutlined, SafetyCertificateOutlined } from '@ant-design/icons';
import { api } from './api';
import AnswerCard, { displayNumber } from './AnswerCard';
import type { Answer, Catalog, Conversation, Health, ImportHistory, ImportPreview } from './types';

const examples = [
  { tag: '收入查询', title: '心内科一年的收入是多少？', question: '2025年心内科总收入是多少？', icon: '01' },
  { tag: '科室对比', title: '哪个科室的收入最高？', question: '2026年4月各科室收入从高到低排名', icon: '02' },
  { tag: '经营趋势', title: '看看心内科的月度收入走势', question: '2025年心内科每月收入走势，按万元展示', icon: '03' },
  { tag: '医保分析', title: '内科的医保占比有多少？', question: '2025年内科的医保占比是多少？', icon: '04' },
];
type Page = 'chat' | 'data' | 'catalog';

export default function App() {
  const { message } = AntApp.useApp();
  const [page, setPage] = useState<Page>('chat');
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [health, setHealth] = useState<Health | null>(null);
  const [error, setError] = useState('');
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [answers, setAnswers] = useState<Answer[]>([]);
  const [question, setQuestion] = useState('');
  const [busy, setBusy] = useState(false);
  const [loadingConversation, setLoadingConversation] = useState(false);
  const [pendingQuestion, setPendingQuestion] = useState('');
  const endRef = useRef<HTMLDivElement>(null);
  const busyRef = useRef(false);

  const refresh = useCallback(async () => {
    try {
      const [data, status, history] = await Promise.all([api<Catalog>('/catalog'), api<Health>('/health'), api<Conversation[]>('/conversations')]);
      setCatalog(data); setHealth(status); setConversations(history); setError('');
    } catch (e) { setError((e as Error).message); }
  }, []);
  useEffect(() => { void refresh(); }, [refresh]);
  useEffect(() => { if (answers.length || busy) endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' }); }, [answers.length, busy]);

  async function ask(text: string) {
    text = text.trim();
    if (!text || busyRef.current) return;
    busyRef.current = true; setBusy(true); setPendingQuestion(text); setQuestion(''); setPage('chat');
    try {
      const answer = await api<Answer>('/chat', { method: 'POST', body: JSON.stringify({ question: text, conversation_id: conversationId }) });
      setAnswers(a => [...a, answer]); setConversationId(answer.conversation_id);
      if (answer.status === 'error') setQuestion(text);
      setConversations(await api<Conversation[]>('/conversations'));
    } catch (e) { message.error((e as Error).message); setQuestion(text); }
    finally { setBusy(false); busyRef.current = false; setPendingQuestion(''); }
  }
  async function openConversation(id: string) {
    if (busyRef.current) return;
    setLoadingConversation(true); setPage('chat');
    try {
      const conv = await api<{ id: string; messages: Answer[] }>(`/conversations/${id}`);
      setConversationId(id); setAnswers(conv.messages); setQuestion('');
    } catch (e) { message.error((e as Error).message); }
    finally { setLoadingConversation(false); }
  }
  function newConversation() { if (!busy) { setConversationId(null); setAnswers([]); setQuestion(''); setPage('chat'); } }
  const hasChat = answers.length > 0 || busy;

  return <div className="app-shell">
    <aside className="sidebar">
      <a className="brand" href="#" onClick={e => { e.preventDefault(); newConversation(); }}><span className="brand-mark"><span /><span /><span /><span /></span><div><strong>院数<span className="brand-dot">.</span></strong><small>HOSPITAL INSIGHT</small></div></a>
      <div className="workspace-label">工作空间 <span>LOCAL</span></div>
      <nav aria-label="主导航">{([{ key: 'chat', name: '智能问数', icon: <MessageOutlined /> }, { key: 'data', name: '数据管理', icon: <DatabaseOutlined /> }, { key: 'catalog', name: '指标说明', icon: <BookOutlined /> }] as const).map(item => <button key={item.key} aria-label={item.name} title={item.name} className={'nav-item ' + (page === item.key ? 'active' : '')} onClick={() => setPage(item.key)}>{item.icon}<span>{item.name}</span>{page === item.key && <span className="nav-active-dot" />}</button>)}</nav>
      <Button className="new-chat" icon={<PlusOutlined />} block onClick={newConversation} disabled={busy || loadingConversation}>开启新对话</Button>
      <div className="history-heading"><span>最近对话</span><HistoryOutlined /></div>
      <div className="history-list">{conversations.length ? conversations.map(c => <button disabled={busy || loadingConversation} title={c.title} key={c.id} className={conversationId === c.id ? 'selected' : ''} onClick={() => void openConversation(c.id)}><MessageOutlined /><span>{c.title}</span></button>) : <div className="history-empty">你的提问会保存在这里</div>}</div>
      <div className="sidebar-bottom"><div className="local-card"><SafetyCertificateOutlined /><div><strong>数据保存在本地</strong><small>计算有口径，答案有出处</small></div></div><div className="profile"><span className="avatar">院</span><div><strong>个人工作空间</strong><small>本地版本 · v1.0</small></div><span className="connection-dot" /></div></div>
    </aside>
    <main className="main-content">
      <header className="topbar"><div><span className="breadcrumb">工作空间</span><span className="breadcrumb-slash">/</span><strong>{{ chat: '智能问数', data: '数据管理', catalog: '指标说明' }[page]}</strong></div><div className="topbar-right"><span className="data-online"><span className={'connection-dot ' + (error ? 'offline' : '')} />{error ? '连接未就绪' : catalog ? '本地数据已连接' : '正在连接'}</span><span className="topbar-divider" /><Tag bordered={false} color={health?.mode === 'cloud' ? 'green' : 'default'}>{health?.mode === 'cloud' ? '云端模型' : '离线演示模式'}</Tag></div></header>
      <div className={'page-content ' + (hasChat && page === 'chat' ? 'conversation-page' : '')}>
        {error && <Alert type="error" showIcon message="无法连接本地服务" description={error} action={<Button onClick={() => void refresh()} icon={<ReloadOutlined />}>重试</Button>} />}
        {health?.mode === 'cloud' && !health.model_configured && <Alert type="warning" showIcon message="云端模型尚未配置" description="请在项目 .env 中填写模型地址、名称和密钥后重启。数据管理和指标说明仍可使用。" />}
        {!catalog && !error && <div className="page-loading"><Spin size="large" /><p>正在读取本地数据…</p></div>}
        {page === 'chat' && catalog && <>
          {!hasChat && <>
            <div className="hero"><div className="eyebrow"><span /> 科室经营数据助手</div><h1>让每一次提问，<br />都有<span>数据依据。</span></h1><p>用日常语言，了解科室收入、医保构成与经营趋势。<br className="desktop-break" />从一个问题开始，找到表格里的答案。</p><div className="hero-decoration" aria-hidden="true"><div className="deco-grid"/><div className="deco-bars"><i/><i/><i/><i/><i/></div><div className="deco-badge"><CheckCircleFilled /> 可追溯的数据</div></div></div>
            <div className="dataset-strip"><div className="dataset-icon"><FileExcelOutlined /></div><div className="dataset-name"><strong>科室月度经营数据</strong><span>{catalog.start_month && catalog.end_month ? `${catalog.start_month} — ${catalog.end_month}` : '尚未导入数据'}</span></div><div className="dataset-stat"><strong>{catalog.departments.length}</strong><span>个科室</span></div><div className="dataset-stat"><strong>{catalog.row_count}</strong><span>条记录</span></div><div className="dataset-stat"><strong>{catalog.months.length}</strong><span>个月份</span></div><Button type="text" className="dataset-link" onClick={() => setPage('data')}>查看数据 <ArrowRightOutlined /></Button></div>
          </>}
          {hasChat && <div className="conversation-heading"><div className="eyebrow">从数据到答案</div><h2>问数工作台</h2><span className="muted">数据截至 {catalog.end_month} · 支持连续追问</span></div>}
          {loadingConversation ? <div className="page-loading"><Spin /></div> : <div className="messages">{answers.map(answer => <div className="message-turn" key={answer.id}><div className="user-question"><span className="question-avatar">我</span><p>{answer.question}</p></div><AnswerCard answer={answer} onChoice={text => void ask(text)} busy={busy} /></div>)}</div>}
          {busy && <div className="message-turn"><div className="user-question"><span className="question-avatar">我</span><p>{pendingQuestion}</p></div><div className="thinking"><Spin size="small"/><span>{health?.mode === 'cloud' ? '正在理解问题并查询本地数据…' : '正在解析条件并查询本地数据…'}</span></div></div>}
          <div className={'composer-wrap ' + (hasChat ? 'has-messages' : '')}><div className="composer"><Input.TextArea aria-label="输入你的数据问题" placeholder={catalog.row_count ? '例如：2025 年心内科的总收入是多少？' : '请先在数据管理中导入 Excel'} value={question} onChange={e => setQuestion(e.target.value)} onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); void ask(question); } }} autoSize={{ minRows: 2, maxRows: 6 }} maxLength={2000} disabled={busy || !catalog.row_count || loadingConversation} /><div className="composer-bottom"><span><DatabaseOutlined /> 科室月度经营数据 <span className="composer-separator">·</span> {health?.mode === 'demo' ? '规则解析演示' : '云端理解 · 本地计算'}</span><Button type="primary" shape="circle" size="large" aria-label="发送问题" icon={<ArrowUpOutlined />} onClick={() => void ask(question)} disabled={!question.trim() || busy || !catalog.row_count || loadingConversation} loading={busy} /></div></div><div className="composer-hint"><span>{health?.mode === 'demo' ? '当前为离线规则演示，支持下方示例及常见问法；可配置云端模型理解更多表达。' : '原始经营记录和查询结果不发送给模型；问题、字段说明与必要查询上下文会发送。'}</span><span className="keyboard-hint">Enter 发送 · Shift + Enter 换行</span></div></div>
          {!hasChat && <><div className="section-heading"><h3>可以这样问</h3><span>从一个具体问题开始</span></div><div className="example-grid">{examples.map(ex => <button disabled={!catalog.row_count || busy} className="example-card" onClick={() => void ask(ex.question)} key={ex.icon}><div className="example-top"><span>{ex.tag}</span><span className="example-number">{ex.icon}</span></div><strong>{ex.title}</strong><div className="example-bottom"><span>{ex.question.includes('2025') ? '2025 年数据' : '2026 年 4 月数据'}</span><ArrowRightOutlined /></div></button>)}</div><div className="trust-footer"><span><CheckCircleFilled /> 原始表格可追溯</span><span><BarChartOutlined /> 自动生成图表</span><span><MessageOutlined /> 支持连续追问</span></div></>}
          <div ref={endRef} />
        </>}
        {page === 'data' && catalog && <DataPage catalog={catalog} onRefresh={refresh} />}
        {page === 'catalog' && catalog && <CatalogPage catalog={catalog} />}
      </div>
      <footer className="page-footer"><span>院数 · 让科室数据更易读懂</span><span>第一版仅支持科室经营指标，不提供诊疗项目报价。</span></footer>
    </main>
  </div>;
}

function DataPage({ catalog, onRefresh }: { catalog: Catalog; onRefresh: () => Promise<void> }) {
  const { message } = AntApp.useApp();
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [history, setHistory] = useState<ImportHistory[]>([]);
  const [uploading, setUploading] = useState(false);
  const [committing, setCommitting] = useState(false);
  const [overwrite, setOverwrite] = useState(false);
  const [error, setError] = useState('');
  const loadHistory = useCallback(() => api<ImportHistory[]>('/imports').then(setHistory).catch(e => setError(e.message)), []);
  useEffect(() => { void loadHistory(); }, [loadHistory]);
  async function upload(file: File) {
    setUploading(true); setPreview(null); setOverwrite(false); setError('');
    try { const form = new FormData(); form.append('file', file); setPreview(await api<ImportPreview>('/imports/preview', { method: 'POST', body: form })); await loadHistory(); }
    catch (e) { setError((e as Error).message); }
    finally { setUploading(false); }
    return false;
  }
  async function commit() {
    if (!preview) return;
    setCommitting(true); setError('');
    try { await api(`/imports/${preview.id}/commit`, { method: 'POST', body: JSON.stringify({ overwrite_conflicts: overwrite }) }); message.success('导入完成，查询已使用最新数据'); setPreview(null); setOverwrite(false); await onRefresh(); await loadHistory(); }
    catch (e) { setError((e as Error).message); }
    finally { setCommitting(false); }
  }
  return <>
    <PageTitle eyebrow="数据工作台" title="管理每一份数据" description="导入前检查，确认后更新。每个答案都保留原始表格的出处。" />
    <div className="overview-grid">{[{ label: '有效记录', value: catalog.row_count, suffix: '条' }, { label: '科室覆盖', value: catalog.departments.length, suffix: '个' }, { label: '数据截至', value: catalog.end_month || '—', suffix: '' }, { label: '当前版本', value: `v${catalog.revision}`, suffix: '' }].map(item => <div className="overview-card" key={item.label}><span>{item.label}</span><strong>{item.value}<small>{item.suffix}</small></strong></div>)}</div>
    <section className="panel"><div className="panel-title"><h3>导入 Excel</h3><Tag>本地处理</Tag></div><Upload.Dragger accept=".xlsx" multiple={false} showUploadList={false} beforeUpload={file => upload(file)} disabled={uploading || committing}><p className="ant-upload-drag-icon">{uploading ? <Spin /> : <InboxOutlined />}</p><p className="ant-upload-text">{uploading ? '正在检查表格…' : '点击选择，或将 Excel 拖放到这里'}</p><p className="ant-upload-hint">支持与原表相同的 22 列 · .xlsx · 最大 10 MB<br/>同一科室和月份的重复数据会跳过，变更数据需要确认覆盖。</p></Upload.Dragger>{error && <Alert type="error" showIcon message={error} className="result-warning" />}</section>
    {preview && <section className="panel" data-testid="import-preview"><div className="panel-title"><h3>导入预览</h3><span className="muted">{preview.filename}</span></div><div className="preview-stats"><Tag color="green">新增 {preview.new}</Tag><Tag>重复 {preview.duplicates}</Tag><Tag color={preview.conflict_count ? 'orange' : 'default'}>冲突 {preview.conflict_count}</Tag><Tag color={preview.error_count ? 'red' : 'default'}>错误 {preview.error_count}</Tag></div>
      {preview.errors.length > 0 && <Alert type="error" message={`共 ${preview.error_count} 项错误，修正后才能导入`} description={<ul className="error-list">{preview.errors.map((e, i) => <li key={i}>{e}</li>)}</ul>} />}
      {preview.sample.length > 0 && <Table size="small" pagination={false} rowKey={r => r.month + r.department} dataSource={preview.sample} columns={[{ title: '年月', dataIndex: 'month' }, { title: '科室', dataIndex: 'department' }, { title: '合计收入（元）', dataIndex: 'total_revenue', align: 'right', render: displayNumber }]} />}
      {preview.conflict_count > 0 && <><h4>变更记录（最多显示 50 条）</h4><div className="conflict-list">{preview.conflicts.map(c => <div key={c.month + c.department}><strong>{c.month} · {c.department}</strong><span>{c.changes.map(x => `${x.field}：${String(x.before)} → ${String(x.after)}`).join('；')}</span></div>)}</div><Checkbox checked={overwrite} onChange={e => setOverwrite(e.target.checked)}>我已核对变更，确认覆盖上述冲突记录</Checkbox></>}
      <div className="panel-actions"><span className="tiny muted">预览不会改变当前可查询的数据。</span><Button type="primary" onClick={() => void commit()} loading={committing} disabled={!preview.can_commit || (preview.conflict_count > 0 && !overwrite)}>确认导入</Button></div>
    </section>}
    <section className="panel"><div className="panel-title"><h3>导入记录</h3><span className="muted">最近 50 次</span></div><Table size="middle" rowKey="id" dataSource={history} locale={{ emptyText: <Empty description="暂无导入记录" /> }} pagination={{ pageSize: 8, showSizeChanger: false }} scroll={{ x: 600 }} columns={[
      { title: '文件', dataIndex: 'filename', render: name => <span><FileExcelOutlined className="green" /> {name}</span> },
      { title: '时间', dataIndex: 'created_at', render: t => new Date(t).toLocaleString('zh-CN', { hour12: false }) },
      { title: '变更', render: (_, r) => `新增 ${r.summary.new} / 冲突 ${r.summary.conflict_count}` },
      { title: '状态', dataIndex: 'status', render: s => <Tag color={s === 'committed' ? 'green' : s === 'invalid' ? 'red' : 'default'}>{{ committed: '已提交', pending: '待提交', invalid: '校验失败' }[s as string] || s}</Tag> },
      { title: '版本', dataIndex: 'revision', render: v => v != null ? `v${v}` : '—' },
    ]} /></section>
  </>;
}

function PageTitle({ eyebrow, title, description }: { eyebrow: string; title: string; description: string }) {
  return <div className="page-title"><div className="eyebrow">{eyebrow}</div><h1>{title}</h1><p>{description}</p></div>;
}

function CatalogPage({ catalog }: { catalog: Catalog }) {
  const [filter, setFilter] = useState('');
  const rules: Record<string, string> = { sum: '可汇总', ratio: '按金额重算', snapshot: '同月可汇总', raw: '科室月度原值' };
  return <>
    <PageTitle eyebrow="口径与范围" title="先理解指标，再读懂数字" description="字段含义与计算规则公开可查；表格没有的内容，系统会明确说明。" />
    <div className="catalog-intro"><BookOutlined /><div><strong>这份表描述的是医院经营情况</strong><p>收入不等于利润，人次不等于去重人数，次均费用也不能直接当作患者账单。缺少具体诊疗项目价格、成本及患者明细时，不推导这些结果。</p></div></div>
    <section className="panel"><div className="panel-title"><h3>指标字典 <span className="count-badge">{catalog.metrics.length}</span></h3><Input.Search aria-label="搜索指标" placeholder="搜索指标名称或说明" value={filter} onChange={e => setFilter(e.target.value)} style={{ width: 260, maxWidth: '55%' }} allowClear /></div><Table rowKey="id" size="middle" pagination={false} scroll={{ x: 650 }} dataSource={catalog.metrics.filter(m => (m.label + m.description + m.aliases.join('')).includes(filter))} columns={[
      { title: '指标', dataIndex: 'label', width: 160, render: v => <strong>{v}</strong> }, { title: '单位', dataIndex: 'unit', width: 65 },
      { title: '计算方式', dataIndex: 'aggregation', width: 135, render: v => <Tag color={v === 'sum' ? 'green' : 'default'}>{rules[v]}</Tag> },
      { title: '定义与边界', dataIndex: 'description' },
    ]} /></section>
    <section className="panel"><div className="panel-title"><h3>科室与常用说法</h3><span className="muted">别名精确映射</span></div><div className="department-grid">{catalog.departments.map(dept => <div key={dept}><div><strong>{dept}</strong><Tag>{catalog.department_map[dept]}</Tag></div><span>{Object.entries(catalog.aliases).filter(([, d]) => d === dept).map(([alias]) => alias).join('、') || '使用科室全名'}</span></div>)}</div></section>
    <section className="panel"><h3>时间如何理解</h3><div className="time-rules"><p><strong>没有指定时间</strong>使用最新有数据月份 {catalog.end_month}，并在答案中提示。</p><p><strong>今年、上个月</strong>按真实日历计算，超出数据范围时返回无数据。</p><p><strong>最近三个月</strong>指最近三个已经结束的日历月份；“最新三个有数据月份”则以表格末月为准。</p><p><strong>同比与环比</strong>只在两段比较期间都有完整记录时计算；对比期为零时不计算增长率。</p></div></section>
  </>;
}
