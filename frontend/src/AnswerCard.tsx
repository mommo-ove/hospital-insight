import { lazy, Suspense, useState } from 'react';
import { Alert, Button, Drawer, Select, Spin, Table, Tabs, Tag } from 'antd';
import { CheckCircleFilled, DownloadOutlined, FileSearchOutlined, QuestionCircleOutlined, DatabaseOutlined } from '@ant-design/icons';
import type { Answer } from './types';

const QueryChart = lazy(() => import('./QueryChart'));
const statusLabels = { success: '查询完成', clarification: '需要补充信息', no_data: '暂无匹配数据', unsupported: '超出数据范围', error: '查询未完成' };
export const displayNumber = (value: unknown) => typeof value === 'number' ? value.toLocaleString('zh-CN', { maximumFractionDigits: 6 }) : value === null || value === undefined ? '不可计算' : String(value);

export default function AnswerCard({ answer, onChoice, busy }: { answer: Answer; onChoice: (s: string) => void; busy: boolean }) {
  const [sourceOpen, setSourceOpen] = useState(false);
  const [metricId, setMetricId] = useState(answer.chart?.metrics[0]?.key);
  const metric = answer.chart?.metrics.find(m => m.key === metricId) ?? answer.chart?.metrics[0];
  const success = answer.status === 'success';
  return <article className="answer-card">
    <div className="answer-top"><div className="answer-brand"><span className="mini-logo"><DatabaseOutlined /></span><strong>院数</strong><span className={'answer-status ' + answer.status}>{success ? <CheckCircleFilled /> : <QuestionCircleOutlined />} {statusLabels[answer.status]}</span></div><span className="tiny muted">{answer.mode === 'demo' ? '本地演示' : answer.model}</span></div>
    <p className="answer-text">{answer.answer}</p>
    {answer.plan && <div className="query-tags"><Tag>{answer.plan.start_month === answer.plan.end_month ? answer.plan.start_month : `${answer.plan.start_month} — ${answer.plan.end_month}`}</Tag><Tag>{answer.scope || answer.plan.departments.join('、') || '全部科室'}</Tag>{answer.revision != null && <Tag>数据版本 v{answer.revision}</Tag>}</div>}
    {answer.warnings.map(w => <Alert key={w} message={w} type="warning" showIcon className="result-warning" />)}
    {success && !answer.plan?.group_by.length && <div className="value-grid">{answer.columns.filter(c => answer.plan?.metrics.includes(c.key)).map(col => <div className="value-card" key={col.key}><span>{col.label}</span><div><strong>{displayNumber(answer.rows[0]?.[col.key])}</strong><small>{col.unit}</small></div></div>)}</div>}
    {success && <Tabs defaultActiveKey={answer.chart ? 'chart' : 'table'} items={[
      ...(answer.chart && metric ? [{ key: 'chart', label: '可视化', children: <><div className="chart-heading"><span>{metric.label}</span>{answer.chart.metrics.length > 1 && <Select aria-label="图表指标" value={metric.key} onChange={setMetricId} options={answer.chart.metrics.map(m => ({ label: m.label, value: m.key }))} />}</div><Suspense fallback={<div className="chart-loading"><Spin /></div>}><QueryChart answer={answer} metric={metric} /></Suspense></> }] : []),
      { key: 'table', label: `结果表 · ${answer.rows.length}`, children: <Table size="small" scroll={{ x: 'max-content' }} rowKey={(_, index) => String(index)} dataSource={answer.rows} pagination={answer.rows.length > 12 ? { pageSize: 12, showSizeChanger: false } : false} columns={answer.columns.map(col => ({ title: col.label + (col.unit ? `（${col.unit}）` : ''), dataIndex: col.key, render: displayNumber, align: col.unit ? 'right' as const : 'left' as const }))} /> },
    ]} />}
    {answer.choices.length > 0 && <div className="choice-buttons">{answer.choices.map(choice => <Button disabled={busy} onClick={() => onChoice(choice)} key={choice}>{choice}</Button>)}</div>}
    {success && <><div className="metric-notes">{answer.metric_notes?.map(n => <div key={n}>{n}</div>)}</div><div className="answer-footer"><span><CheckCircleFilled /> 由本地数据计算 · {answer.sources.length} 条来源记录</span><div><Button type="text" size="small" icon={<FileSearchOutlined />} onClick={() => setSourceOpen(true)}>查看依据</Button><Button type="text" size="small" icon={<DownloadOutlined />} href={`/api/queries/${answer.id}/export`}>导出 CSV</Button></div></div></>}
    <Drawer title="查询依据" width={Math.min(840, window.innerWidth)} open={sourceOpen} onClose={() => setSourceOpen(false)}>
      <p className="muted">以下为此次查询时保存的数据快照；后续导入不会改变这份历史依据。</p>
      <Tabs items={[
        { key: 'source', label: `Excel 来源 (${answer.sources.length})`, children: <Table size="small" rowKey={r => `${r.import_id}-${r.row}`} dataSource={answer.sources} pagination={{ pageSize: 10, showSizeChanger: false }} scroll={{ x: 560 }} columns={[
          { title: '文件 / 工作表', render: (_, r) => <><strong>{r.file}</strong><div className="tiny muted">{r.sheet}</div></> },
          { title: '原始行', dataIndex: 'row', width: 78 }, { title: '版本', dataIndex: 'version', width: 65 },
          { title: '科室 / 年月', render: (_, r) => <>{String(r.values.department)}<div className="tiny muted">{String(r.values.month).slice(0, 7)}</div></> },
        ]} expandable={{ expandedRowRender: r => <><div className="source-cells">{Object.entries(r.cells).map(([key, cell]) => <div key={key}><code>{cell}</code><span>{displayNumber(r.values[key])}</span></div>)}</div><p className="hash">SHA-256: {r.sha256}</p></> }} /> },
        { key: 'sql', label: 'SQL 与参数', children: <>{answer.sql.map(s => <section className="sql-section" key={s.label}><h4>{s.label}</h4><pre>{s.statement}</pre><pre>{JSON.stringify(s.parameters, null, 2)}</pre></section>)}<Alert message="SQL 由后端依据白名单生成；排序、结果截断和展示单位转换在本地进行。" type="info" /></> },
        { key: 'plan', label: '查询条件', children: <pre>{JSON.stringify(answer.plan, null, 2)}</pre> },
      ]} />
    </Drawer>
  </article>;
}
