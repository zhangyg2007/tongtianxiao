import { Tag, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { Link } from 'react-router-dom';
import { fmtTime, PRODUCT_LINE } from '../status';
import type { ArtifactRow, TaskRow } from '../types';
import TaskStatusTag from './StatusTag';

/** 任务列表列（任务列表页 / 对象详情页共用）。 */
export const taskColumns: ColumnsType<TaskRow> = [
  {
    title: '任务 ID',
    dataIndex: 'task_id',
    width: 150,
    render: (v: string) => (
      <Link to={`/tasks/${v}`}>
        <Typography.Text style={{ fontFamily: 'monospace' }}>{v.slice(0, 8)}</Typography.Text>
      </Link>
    ),
  },
  {
    title: '产品线',
    dataIndex: 'product_line',
    width: 80,
    render: (v: string) => {
      const m = PRODUCT_LINE[v];
      return <Tag color={m?.color}>{m?.label ?? v}</Tag>;
    },
  },
  { title: '类型', dataIndex: 'task_type', width: 150 },
  {
    title: '状态',
    dataIndex: 'status',
    width: 90,
    render: (v: string) => <TaskStatusTag status={v} />,
  },
  {
    title: '进度',
    dataIndex: 'progress',
    width: 70,
    render: (v: number) => `${v}%`,
  },
  {
    title: '阶段',
    dataIndex: 'stage',
    ellipsis: true,
    render: (v: string | null) => v ?? '—',
  },
  {
    title: '创建时间',
    dataIndex: 'created_at',
    width: 160,
    render: (v: string) => fmtTime(v),
  },
];

/** 产物列表列。 */
export const artifactColumns: ColumnsType<ArtifactRow> = [
  {
    title: '标题',
    dataIndex: 'title',
    ellipsis: true,
    render: (v: string | null) => v ?? '（无标题）',
  },
  { title: '类型', dataIndex: 'artifact_type', width: 110 },
  {
    title: '模板',
    dataIndex: 'template_code',
    width: 140,
    render: (v: string | null) => v ?? '—',
  },
  { title: '版本', dataIndex: 'version', width: 60 },
  {
    title: '状态',
    dataIndex: 'status',
    width: 90,
    render: (v: string) => <Tag>{v}</Tag>,
  },
  {
    title: '生成时间',
    dataIndex: 'created_at',
    width: 160,
    render: (v: string) => fmtTime(v),
  },
];
