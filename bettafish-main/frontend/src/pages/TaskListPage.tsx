import { ReloadOutlined } from '@ant-design/icons';
import { Button, Card, Select, Space, Table, message } from 'antd';
import { useCallback, useEffect, useState } from 'react';
import { api } from '../api/client';
import { TASK_STATUS } from '../status';
import type { TaskRow } from '../types';
import { taskColumns } from '../components/tables';

const PRODUCT_LINE_OPTIONS = [
  { value: 'dd', label: '背调' },
  { value: 'pr', label: '舆情' },
];

const STATUS_OPTIONS = Object.entries(TASK_STATUS).map(([value, m]) => ({
  value,
  label: m.label,
}));

export default function TaskListPage() {
  const [rows, setRows] = useState<TaskRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [productLine, setProductLine] = useState<string | undefined>();
  const [status, setStatus] = useState<string | undefined>();

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.listTasks({ product_line: productLine, status });
      setRows(res.tasks);
    } catch (e) {
      message.error(e instanceof Error ? e.message : '加载失败');
    } finally {
      setLoading(false);
    }
  }, [productLine, status]);

  useEffect(() => {
    void load();
  }, [load]);

  // 5 秒自动刷新（运行中任务的进度会自动更新）
  useEffect(() => {
    const timer = setInterval(() => void load(), 5000);
    return () => clearInterval(timer);
  }, [load]);

  return (
    <Card
      title="任务列表"
      extra={
        <Space>
          <Select
            allowClear
            placeholder="产品线"
            style={{ width: 110 }}
            options={PRODUCT_LINE_OPTIONS}
            onChange={(v) => setProductLine(v)}
          />
          <Select
            allowClear
            placeholder="状态"
            style={{ width: 110 }}
            options={STATUS_OPTIONS}
            onChange={(v) => setStatus(v)}
          />
          <Button icon={<ReloadOutlined />} onClick={() => void load()}>
            刷新
          </Button>
        </Space>
      }
    >
      <Table
        rowKey="task_id"
        loading={loading}
        dataSource={rows}
        columns={taskColumns}
        pagination={{ pageSize: 20 }}
      />
    </Card>
  );
}
