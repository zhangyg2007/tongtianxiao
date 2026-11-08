import { Tag } from 'antd';
import { TASK_STATUS } from '../status';

export default function TaskStatusTag({ status }: { status: string }) {
  const meta = TASK_STATUS[status] ?? { label: status, color: 'default' };
  return <Tag color={meta.color}>{meta.label}</Tag>;
}
