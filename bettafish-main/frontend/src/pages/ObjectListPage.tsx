import { PlusOutlined, ReloadOutlined, SearchOutlined } from '@ant-design/icons';
import { Button, Card, Form, Input, message, Modal, Select, Space, Table, Tag } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useCallback, useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { api } from '../api/client';
import { fmtTime, OBJECT_TYPE } from '../status';
import type { ObjectRow } from '../types';
import TaskLaunchModal from '../components/TaskLaunchModal';

const columns: ColumnsType<ObjectRow> = [
  { title: 'ID', dataIndex: 'object_id', width: 70 },
  {
    title: '对象',
    dataIndex: 'display_name',
    render: (_: string, row: ObjectRow) => (
      <div>
        <Link to={`/objects/${row.object_id}`}>
          <strong>{row.display_name}</strong>
        </Link>
        {row.display_meta && (
          <div style={{ color: '#888', fontSize: 12 }}>{row.display_meta}</div>
        )}
      </div>
    ),
  },
  {
    title: '类型',
    dataIndex: 'object_type',
    width: 90,
    render: (t: string) => {
      const m = OBJECT_TYPE[t];
      return <Tag color={m?.color}>{m?.label ?? t}</Tag>;
    },
  },
  {
    title: 'natural_key',
    dataIndex: 'natural_key',
    width: 190,
    ellipsis: true,
    render: (v: string | null) => v ?? '—',
  },
  {
    title: '更新时间',
    dataIndex: 'updated_at',
    width: 170,
    render: (v: string) => fmtTime(v),
  },
];

export default function ObjectListPage() {
  const [rows, setRows] = useState<ObjectRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [q, setQ] = useState('');
  const [createOpen, setCreateOpen] = useState(false);
  const [launchTarget, setLaunchTarget] = useState<ObjectRow | null>(null);
  const [form] = Form.useForm();
  const navigate = useNavigate();

  const load = useCallback(async (keyword: string) => {
    setLoading(true);
    try {
      const res = await api.listObjects(keyword);
      setRows(res.objects);
    } catch (e) {
      message.error(e instanceof Error ? e.message : '加载失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load('');
  }, [load]);

  const handleCreate = async () => {
    let values: Record<string, unknown>;
    try {
      values = await form.validateFields();
    } catch {
      return;
    }
    try {
      await api.createObject(values as Parameters<typeof api.createObject>[0]);
      message.success('对象已注册');
      form.resetFields();
      setCreateOpen(false);
      void load(q);
    } catch (e) {
      if (e instanceof Error) message.error(e.message);
    }
  };

  return (
    <Card
      title="案卷列表（对象档案）"
      extra={
        <Space>
          <Input
            allowClear
            prefix={<SearchOutlined />}
            placeholder="搜索对象名称"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onPressEnter={() => void load(q)}
            style={{ width: 220 }}
          />
          <Button icon={<ReloadOutlined />} onClick={() => void load(q)}>
            刷新
          </Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>
            注册对象
          </Button>
        </Space>
      }
    >
      <Table
        rowKey="object_id"
        loading={loading}
        dataSource={rows}
        columns={columns}
        pagination={{ pageSize: 20 }}
        locale={{ emptyText: '暂无对象，点击右上角「注册对象」创建' }}
        onRow={(row) => ({
          onClick: () => navigate(`/objects/${row.object_id}`),
          style: { cursor: 'pointer' },
        })}
      />

      <Modal
        open={createOpen}
        title="注册对象"
        okText="注册"
        cancelText="取消"
        onOk={handleCreate}
        onCancel={() => {
          form.resetFields();
          setCreateOpen(false);
        }}
        destroyOnClose
      >
        <Form form={form} layout="vertical">
          <Form.Item
            name="object_type"
            label="对象类型"
            rules={[{ required: true, message: '请选择对象类型' }]}
            initialValue="company"
          >
            <Select
              options={[
                { value: 'company', label: '公司' },
                { value: 'person', label: '人物' },
                { value: 'event', label: '事件' },
              ]}
            />
          </Form.Item>
          <Form.Item
            name="display_name"
            label="名称"
            rules={[{ required: true, message: '请输入名称' }]}
          >
            <Input placeholder="公司全称 / 人名 / 事件标题" />
          </Form.Item>
          <Form.Item
            name="natural_key"
            label="唯一键（可选，公司填统一社会信用代码，幂等）"
          >
            <Input placeholder="USCC / 其他稳定标识" />
          </Form.Item>
          <Form.Item name="display_meta" label="消歧后缀（可选）">
            <Input placeholder="注册地+成立年（公司）、任职公司（人）" />
          </Form.Item>
        </Form>
      </Modal>

      <TaskLaunchModal
        open={launchTarget != null}
        onClose={() => setLaunchTarget(null)}
        objectId={launchTarget?.object_id ?? null}
        objectName={launchTarget?.display_name}
      />
    </Card>
  );
}
