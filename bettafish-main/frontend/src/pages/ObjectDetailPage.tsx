import { PlusOutlined, ReloadOutlined } from '@ant-design/icons';
import { Alert, Button, Card, Descriptions, message, Space, Table, Tabs, Tag } from 'antd';
import { useCallback, useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { api } from '../api/client';
import { fmtTime, OBJECT_TYPE } from '../status';
import type { ArtifactRow, EvidenceRow, ObjectRow, TaskRow } from '../types';
import EvidenceDrawer, { evidenceColumns } from '../components/EvidenceDrawer';
import TaskLaunchModal from '../components/TaskLaunchModal';
import { artifactColumns, taskColumns } from '../components/tables';

export default function ObjectDetailPage() {
  const { id } = useParams();
  const objectId = Number(id);
  const [object, setObject] = useState<ObjectRow | null>(null);
  const [tasks, setTasks] = useState<TaskRow[]>([]);
  const [artifacts, setArtifacts] = useState<ArtifactRow[]>([]);
  const [evidence, setEvidence] = useState<EvidenceRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [selected, setSelected] = useState<EvidenceRow | null>(null);
  const [launchOpen, setLaunchOpen] = useState(false);

  const load = useCallback(async () => {
    if (!Number.isFinite(objectId)) return;
    setLoading(true);
    try {
      const [detail, ev] = await Promise.all([
        api.getObject(objectId),
        api.listEvidence({ object_id: objectId }),
      ]);
      setObject(detail.object);
      setTasks(detail.tasks);
      setArtifacts(detail.artifacts);
      setEvidence(ev.evidence);
    } catch (e) {
      message.error(e instanceof Error ? e.message : '加载失败');
    } finally {
      setLoading(false);
    }
  }, [objectId]);

  useEffect(() => {
    void load();
  }, [load]);

  if (!Number.isFinite(objectId)) return null;
  if (!object) return <Card loading />;

  const typeMeta = OBJECT_TYPE[object.object_type];

  return (
    <Card
      title={
        <Space>
          <strong style={{ fontSize: 16 }}>{object.display_name}</strong>
          <Tag color={typeMeta?.color}>{typeMeta?.label ?? object.object_type}</Tag>
        </Space>
      }
      extra={
        <Space>
          <Button icon={<ReloadOutlined />} onClick={() => void load()}>
            刷新
          </Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setLaunchOpen(true)}>
            发起任务
          </Button>
        </Space>
      }
    >
      <Descriptions column={2} size="small" style={{ marginBottom: 16 }}>
        <Descriptions.Item label="对象 ID">{object.object_id}</Descriptions.Item>
        <Descriptions.Item label="消歧后缀">
          {object.display_meta ?? '—'}
        </Descriptions.Item>
        <Descriptions.Item label="natural_key">
          {object.natural_key ?? '—'}
        </Descriptions.Item>
        <Descriptions.Item label="更新时间">{fmtTime(object.updated_at)}</Descriptions.Item>
      </Descriptions>

      <Tabs
        items={[
          {
            key: 'tasks',
            label: `任务记录（${tasks.length}）`,
            children: (
              <Table
                rowKey="task_id"
                size="small"
                dataSource={tasks}
                columns={taskColumns}
                pagination={{ pageSize: 10 }}
                locale={{ emptyText: '暂无任务，点击右上角「发起任务」' }}
              />
            ),
          },
          {
            key: 'artifacts',
            label: `产物（${artifacts.length}）`,
            children: (
              <Table
                rowKey="artifact_id"
                size="small"
                dataSource={artifacts}
                columns={artifactColumns}
                pagination={false}
                locale={{ emptyText: '暂无产物' }}
              />
            ),
          },
          {
            key: 'evidence',
            label: `证据（${evidence.length}）`,
            children: (
              <>
                <Alert
                  type="info"
                  showIcon
                  style={{ marginBottom: 12 }}
                  message="P0 验收：随机点击任一证据，应能直接看到原文片段与原文出处链接。"
                />
                <Table
                  rowKey="evidence_id"
                  size="small"
                  dataSource={evidence}
                  columns={evidenceColumns}
                  pagination={{ pageSize: 10 }}
                  locale={{ emptyText: '暂无证据（对挂在本对象上的任务执行 demo_pipeline 可生成样例证据）' }}
                  onRow={(row) => ({
                    onClick: () => setSelected(row),
                    style: { cursor: 'pointer' },
                  })}
                />
              </>
            ),
          },
        ]}
      />

      <EvidenceDrawer
        evidence={selected}
        open={selected != null}
        onClose={() => setSelected(null)}
      />

      <TaskLaunchModal
        open={launchOpen}
        onClose={() => setLaunchOpen(false)}
        objectId={object.object_id}
        objectName={object.display_name}
      />
    </Card>
  );
}
