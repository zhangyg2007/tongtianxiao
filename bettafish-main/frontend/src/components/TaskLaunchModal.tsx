import { Form, Input, InputNumber, message, Modal, Radio, Select } from 'antd';
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../api/client';

const TASK_TYPES = [
  { value: 'demo_pipeline', label: 'demo_pipeline · 链路验证演示' },
  { value: 'insight_research', label: 'insight_research · 舆情深度研究' },
  { value: 'investment_dd', label: 'investment_dd · 投资尽调报告（12 章）' },
];

interface Props {
  open: boolean;
  onClose: () => void;
  objectId: number | null;
  objectName?: string;
}

/** 发起任务弹窗（案卷列表 / 对象详情共用）。 */
export default function TaskLaunchModal({ open, onClose, objectId, objectName }: Props) {
  const [form] = Form.useForm();
  const [submitting, setSubmitting] = useState(false);
  const navigate = useNavigate();
  const taskType = Form.useWatch('task_type', form);

  const handleOk = async () => {
    let values: Record<string, unknown>;
    try {
      values = await form.validateFields();
    } catch {
      return; // 校验失败，错误已显示在字段上
    }
    setSubmitting(true);
    try {
      const input: Record<string, unknown> = {};
      if (values.task_type === 'insight_research') {
        input.query = values.query;
      }
      if (values.task_type === 'demo_pipeline' && values.step_seconds != null) {
        input.step_seconds = values.step_seconds;
      }
      const res = await api.createTask({
        product_line: values.product_line as 'dd' | 'pr',
        task_type: values.task_type as string,
        input,
        object_id: objectId ?? undefined,
      });
      form.resetFields();
      onClose();
      navigate(`/tasks/${res.task_id}`);
    } catch (e) {
      if (e instanceof Error) message.error(e.message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal
      open={open}
      title={
        objectId != null
          ? `发起任务 · ${objectName ?? `对象 ${objectId}`}`
          : '发起任务'
      }
      okText="提交"
      cancelText="取消"
      confirmLoading={submitting}
      onOk={handleOk}
      onCancel={() => {
        form.resetFields();
        onClose();
      }}
      destroyOnClose
    >
      <Form
        form={form}
        layout="vertical"
        initialValues={{ product_line: 'dd', task_type: 'demo_pipeline' }}
      >
        <Form.Item name="product_line" label="产品线" rules={[{ required: true }]}>
          <Radio.Group>
            <Radio.Button value="dd">背调（dd）</Radio.Button>
            <Radio.Button value="pr">舆情（pr）</Radio.Button>
          </Radio.Group>
        </Form.Item>
        <Form.Item name="task_type" label="任务类型" rules={[{ required: true }]}>
          <Select options={TASK_TYPES} />
        </Form.Item>
        {taskType === 'insight_research' && (
          <Form.Item
            name="query"
            label="研究问题（query）"
            rules={[{ required: true, message: '请输入研究问题' }]}
          >
            <Input.TextArea
              rows={3}
              placeholder="例如：某公司近期负面舆情的归因分析"
            />
          </Form.Item>
        )}
        {taskType === 'demo_pipeline' && (
          <Form.Item name="step_seconds" label="每步等待秒数（可选，默认 2）">
            <InputNumber min={0} max={60} style={{ width: '100%' }} />
          </Form.Item>
        )}
      </Form>
    </Modal>
  );
}
