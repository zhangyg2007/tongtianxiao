import {
  Alert,
  Button,
  Card,
  Descriptions,
  Empty,
  message,
  Progress,
  Result,
  Space,
  Table,
  Timeline,
  Typography,
} from 'antd';
import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { api } from '../api/client';
import { fmtTime, PRODUCT_LINE, TERMINAL_STATUSES } from '../status';
import type { ArtifactRow, EvidenceRow, StepRow, TaskRow } from '../types';
import EvidenceDrawer, { evidenceColumns } from '../components/EvidenceDrawer';
import TaskStatusTag from '../components/StatusTag';
import { artifactColumns } from '../components/tables';

export default function TaskDetailPage() {
  const { id } = useParams();
  const taskId = id ?? '';
  const [task, setTask] = useState<TaskRow | null>(null);
  const [steps, setSteps] = useState<StepRow[]>([]);
  const [artifacts, setArtifacts] = useState<ArtifactRow[]>([]);
  const [evidence, setEvidence] = useState<EvidenceRow[]>([]);
  const [selected, setSelected] = useState<EvidenceRow | null>(null);
  const [cancelling, setCancelling] = useState(false);
  const [notFound, setNotFound] = useState(false);

  // 终态后拉取产物与证据
  const loadSide = async (t: TaskRow | null) => {
    if (!t || !TERMINAL_STATUSES.includes(t.status)) return;
    try {
      const [art, ev] = await Promise.all([
        api.listArtifacts({ task_id: taskId }),
        api.listEvidence({ task_id: taskId }),
      ]);
      setArtifacts(art.artifacts);
      setEvidence(ev.evidence);
    } catch {
      // 忽略：详情主体已可见
    }
  };

  // 初始全量 + 404 判定
  useEffect(() => {
    let cancelled = false;
    setNotFound(false);
    setTask(null);
    setSteps([]);
    setArtifacts([]);
    setEvidence([]);
    api
      .getTask(taskId)
      .then((res) => {
        if (cancelled) return;
        setTask(res.task);
        setSteps(res.steps);
        void loadSide(res.task);
      })
      .catch(() => {
        if (!cancelled) setNotFound(true);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [taskId]);

  // SSE：task / step / end 结构化事件（首连全量快照，断线重连自动补齐）
  useEffect(() => {
    const es = new EventSource(`/api/v1/tasks/${taskId}/events`);
    const onTask = (e: Event) => {
      setTask(JSON.parse((e as MessageEvent).data) as TaskRow);
    };
    const onStep = (e: Event) => {
      const step = JSON.parse((e as MessageEvent).data) as StepRow;
      setSteps((prev) => {
        const idx = prev.findIndex((s) => s.seq === step.seq);
        if (idx === -1) return [...prev, step].sort((a, b) => a.seq - b.seq);
        const next = [...prev];
        next[idx] = step;
        return next;
      });
    };
    const onEnd = () => {
      es.close();
      api
        .getTask(taskId)
        .then((res) => {
          setTask(res.task);
          void loadSide(res.task);
        })
        .catch(() => undefined);
    };
    es.addEventListener('task', onTask);
    es.addEventListener('step', onStep);
    es.addEventListener('end', onEnd);
    return () => es.close();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [taskId]);

  const handleCancel = async () => {
    setCancelling(true);
    try {
      await api.cancelTask(taskId);
      message.success('已发送取消请求');
    } catch (e) {
      if (e instanceof Error) message.error(e.message);
    } finally {
      setCancelling(false);
    }
  };

  if (notFound) return <Result status="404" title="任务不存在" />;
  if (!task) return <Card loading />;

  const isTerminal = TERMINAL_STATUSES.includes(task.status);
  const lineMeta = PRODUCT_LINE[task.product_line];

  return (
    <Space direction="vertical" size="middle" style={{ width: '100%' }}>
      <Card
        title={
          <Space>
            <Typography.Text copyable style={{ fontFamily: 'monospace' }}>
              {task.task_id.slice(0, 8)}
            </Typography.Text>
            <TaskStatusTag status={task.status} />
          </Space>
        }
        extra={
          !isTerminal && (
            <Button danger loading={cancelling} onClick={handleCancel}>
              取消任务
            </Button>
          )
        }
      >
        <Descriptions column={2} size="small">
          <Descriptions.Item label="产品线">{lineMeta?.label ?? task.product_line}</Descriptions.Item>
          <Descriptions.Item label="任务类型">{task.task_type}</Descriptions.Item>
          <Descriptions.Item label="对象">
            {task.object_id != null ? (
              <Link to={`/objects/${task.object_id}`}>对象 {task.object_id}</Link>
            ) : (
              '—'
            )}
          </Descriptions.Item>
          <Descriptions.Item label="创建时间">{fmtTime(task.created_at)}</Descriptions.Item>
          <Descriptions.Item label="开始时间">{fmtTime(task.started_at)}</Descriptions.Item>
          <Descriptions.Item label="结束时间">{fmtTime(task.finished_at)}</Descriptions.Item>
        </Descriptions>

        <div style={{ margin: '16px 0 8px' }}>
          <Progress
            percent={task.progress}
            status={
              task.status === 'failed'
                ? 'exception'
                : task.status === 'succeeded'
                  ? 'success'
                  : 'active'
            }
          />
          {task.stage && <div style={{ color: '#666' }}>{task.stage}</div>}
        </div>

        {task.status === 'failed' && task.error && (
          <Alert
            type="error"
            showIcon
            message={`[${task.error.code ?? 'error'}] ${task.error.message ?? ''}`}
          />
        )}
      </Card>

      <Card title="执行步骤（SSE 实时）" size="small">
        {steps.length === 0 ? (
          <Empty description="暂无步骤" image={Empty.PRESENTED_IMAGE_SIMPLE} />
        ) : (
          <Timeline
            items={steps.map((s) => ({
              color:
                s.status === 'succeeded'
                  ? 'green'
                  : s.status === 'failed'
                    ? 'red'
                    : 'blue',
              children: (
                <div>
                  <div>
                    <strong>
                      {s.seq}. {s.name}
                    </strong>{' '}
                    <TaskStatusTag status={s.status} />
                  </div>
                  <div style={{ color: '#888', fontSize: 12 }}>
                    {fmtTime(s.started_at)} ~ {fmtTime(s.finished_at)}
                    {s.duration_ms != null
                      ? ` · ${(s.duration_ms / 1000).toFixed(1)}s`
                      : ''}
                  </div>
                  {s.status === 'failed' && s.detail?.error != null && (
                    <div style={{ color: 'red', fontSize: 12 }}>
                      {String(s.detail.error)}
                    </div>
                  )}
                </div>
              ),
            }))}
          />
        )}
      </Card>

      <Card title={`产物（${artifacts.length}）`} size="small">
        <Table
          rowKey="artifact_id"
          size="small"
          pagination={false}
          dataSource={artifacts}
          columns={artifactColumns}
          locale={{ emptyText: '暂无产物' }}
        />
      </Card>

      <Card
        title={`证据（${evidence.length}）——点击行查看原文出处`}
        size="small"
      >
        <Table
          rowKey="evidence_id"
          size="small"
          pagination={false}
          dataSource={evidence}
          columns={evidenceColumns}
          locale={{ emptyText: '暂无证据' }}
          onRow={(row) => ({
            onClick: () => setSelected(row),
            style: { cursor: 'pointer' },
          })}
        />
      </Card>

      {task.result && Object.keys(task.result).length > 0 && (
        <Card title="结果摘要" size="small">
          <pre style={{ maxHeight: 320, overflow: 'auto', fontSize: 12 }}>
            {JSON.stringify(task.result, null, 2)}
          </pre>
        </Card>
      )}

      <EvidenceDrawer
        evidence={selected}
        open={selected != null}
        onClose={() => setSelected(null)}
      />
    </Space>
  );
}
