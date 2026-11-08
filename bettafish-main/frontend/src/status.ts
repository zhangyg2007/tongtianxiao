/** 状态/枚举的中文名与颜色（AntD Tag color）。 */

export const TASK_STATUS: Record<string, { label: string; color: string }> = {
  queued: { label: '排队中', color: 'default' },
  running: { label: '执行中', color: 'processing' },
  waiting_input: { label: '等待输入', color: 'warning' },
  succeeded: { label: '已成功', color: 'success' },
  failed: { label: '失败', color: 'error' },
  canceled: { label: '已取消', color: 'warning' },
};

export const PRODUCT_LINE: Record<string, { label: string; color: string }> = {
  dd: { label: '背调', color: 'geekblue' },
  pr: { label: '舆情', color: 'purple' },
};

export const OBJECT_TYPE: Record<string, { label: string; color: string }> = {
  company: { label: '公司', color: 'blue' },
  person: { label: '人物', color: 'cyan' },
  event: { label: '事件', color: 'magenta' },
};

export const TERMINAL_STATUSES = ['succeeded', 'failed', 'canceled'];

export function fmtTime(s: string | null | undefined): string {
  if (!s) return '—';
  return s.replace('T', ' ').slice(0, 19);
}
