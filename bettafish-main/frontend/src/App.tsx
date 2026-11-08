import { FolderOpenOutlined, UnorderedListOutlined } from '@ant-design/icons';
import { Layout, Menu } from 'antd';
import { Link, Route, Routes, useLocation } from 'react-router-dom';
import ObjectDetailPage from './pages/ObjectDetailPage';
import ObjectListPage from './pages/ObjectListPage';
import TaskDetailPage from './pages/TaskDetailPage';
import TaskListPage from './pages/TaskListPage';

const { Sider, Header, Content } = Layout;

export default function App() {
  const location = useLocation();
  const selected = location.pathname.startsWith('/tasks') ? '/tasks' : '/objects';

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider theme="dark" width={200}>
        <div style={{ color: '#fff', padding: '16px', fontSize: 18, fontWeight: 600 }}>
          通天晓
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[selected]}
          items={[
            {
              key: '/objects',
              icon: <FolderOpenOutlined />,
              label: <Link to="/objects">案卷列表</Link>,
            },
            {
              key: '/tasks',
              icon: <UnorderedListOutlined />,
              label: <Link to="/tasks">任务列表</Link>,
            },
          ]}
        />
      </Sider>
      <Layout>
        <Header
          style={{
            background: '#fff',
            padding: '0 24px',
            fontSize: 15,
            color: '#444',
          }}
        >
          双工作台 · P0（背调案卷 / 舆情任务）
        </Header>
        <Content style={{ margin: 24 }}>
          <Routes>
            <Route path="/" element={<ObjectListPage />} />
            <Route path="/objects" element={<ObjectListPage />} />
            <Route path="/objects/:id" element={<ObjectDetailPage />} />
            <Route path="/tasks" element={<TaskListPage />} />
            <Route path="/tasks/:id" element={<TaskDetailPage />} />
          </Routes>
        </Content>
      </Layout>
    </Layout>
  );
}
