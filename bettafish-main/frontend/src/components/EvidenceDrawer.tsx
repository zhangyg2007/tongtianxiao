import { Button, Descriptions, Drawer, Tag, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { fmtTime } from '../status';
import type { EvidenceRow } from '../types';

export const FACT_TYPE_LABELS: Record<string, string> = {
  registration: '工商注册',
  penalty: '行政处罚',
  litigation: '诉讼',
  finance: '财务',
  bid: '招投标',
  ip: '知识产权',
  sentiment: '舆情',
  exec_change: '高管变动',
};

export const SOURCE_TYPE_LABELS: Record<string, string> = {
  gsxt: '国家企业信用信息公示系统',
  creditchina: '信用中国',
  court: '裁判文书/法院公告',
  cninfo: '巨潮资讯',
  tianyancha: '天眼查',
  news: '新闻媒体',
  social: '社交媒体',
};

export function confidenceColor(c: number): string {
  if (c >= 90) return 'green';
  if (c >= 70) return 'blue';
  if (c >= 50) return 'orange';
  return 'red';
}

/** 证据列表列（任务详情页 / 对象详情页共用；行点击打开抽屉）。 */
export const evidenceColumns: ColumnsType<EvidenceRow> = [
  { title: 'ID', dataIndex: 'evidence_id', width: 60 },
  { title: '事实断言', dataIndex: 'fact', ellipsis: true },
  {
    title: '类型',
    dataIndex: 'fact_type',
    width: 100,
    render: (t: string) => <Tag>{FACT_TYPE_LABELS[t] ?? t}</Tag>,
  },
  {
    title: '来源',
    dataIndex: 'source_type',
    width: 150,
    render: (t: string) => SOURCE_TYPE_LABELS[t] ?? t,
  },
  {
    title: '置信度',
    dataIndex: 'confidence',
    width: 90,
    render: (c: number) => <Tag color={confidenceColor(c)}>{c}</Tag>,
  },
  {
    title: '发布时间',
    dataIndex: 'published_at',
    width: 110,
    render: (v: string | null) => (v ? v.slice(0, 10) : '—'),
  },
];

interface Props {
  evidence: EvidenceRow | null;
  open: boolean;
  onClose: () => void;
}

/**
 * 证据抽屉——P0 验收入口：从报告/证据列表点进来，
 * 30 秒内看到原文片段（quote）+ 原文出处链接。
 */
export default function EvidenceDrawer({ evidence, open, onClose }: Props) {
  return (
    <Drawer
      open={open}
      onClose={onClose}
      width={560}
      title={evidence ? `证据 #${evidence.evidence_id}` : '证据'}
    >
      {evidence && (
        <>
          <Descriptions column={1} size="small" bordered>
            <Descriptions.Item label="事实断言">
              {evidence.fact}
            </Descriptions.Item>
            <Descriptions.Item label="类型">
              {FACT_TYPE_LABELS[evidence.fact_type] ?? evidence.fact_type}
            </Descriptions.Item>
            <Descriptions.Item label="来源">
              {SOURCE_TYPE_LABELS[evidence.source_type] ?? evidence.source_type}
              {evidence.source_name ? ` · ${evidence.source_name}` : ''}
            </Descriptions.Item>
            <Descriptions.Item label="置信度">
              <Tag color={confidenceColor(evidence.confidence)}>
                {evidence.confidence}
              </Tag>
              {evidence.confidence_reason ?? ''}
            </Descriptions.Item>
            <Descriptions.Item label="发布时间">
              {evidence.published_at ? fmtTime(evidence.published_at) : '—'}
            </Descriptions.Item>
            <Descriptions.Item label="抓取时间">
              {fmtTime(evidence.captured_at)}
            </Descriptions.Item>
          </Descriptions>

          <Typography.Title level={5} style={{ marginTop: 16 }}>
            原文片段
          </Typography.Title>
          <Typography.Paragraph
            copyable={evidence.quote ? true : false}
            style={{
              background: '#fafafa',
              padding: 12,
              borderLeft: '3px solid #1677ff',
              whiteSpace: 'pre-wrap',
            }}
          >
            {evidence.quote ?? '（未保存原文片段）'}
          </Typography.Paragraph>

          <Button
            type="primary"
            href={evidence.source_url}
            target="_blank"
            rel="noreferrer"
          >
            打开原文出处
          </Button>
        </>
      )}
    </Drawer>
  );
}
