import { useState, useEffect } from 'react';
import { StatsDashboard } from './pages/StatsDashboard';
import { MemoryList } from './pages/MemoryList';
import { KnowledgeBase } from './pages/KnowledgeBase';
import { MemoryGraph } from './pages/MemoryGraph';
import { ChatDemo } from './pages/ChatDemo';
import { AgentFlow } from './pages/AgentFlow';
import { Settings } from './pages/Settings';
import { Sub } from './pages/Sub';
import { ScenarioDemo } from './pages/ScenarioDemo';
import { Header } from './components/Header';

type Page = 'chat' | 'scenario' | 'stats' | 'memory' | 'knowledge' | 'graph' | 'agent' | 'settings' | 'sub';

interface Instance {
  id: string;
  name: string;
}

function App() {
  const [currentPage, setCurrentPage] = useState<Page>(() => {
    // Restore page from sessionStorage on initial load
    const saved = sessionStorage.getItem('restorePage') || localStorage.getItem('currentPage');
    sessionStorage.removeItem('restorePage');
    return (saved as Page) || 'chat';
  });
  const [currentInstance, setCurrentInstance] = useState<Instance | null>(null);

  // Save current page to localStorage when it changes
  useEffect(() => {
    localStorage.setItem('currentPage', currentPage);
  }, [currentPage]);

  useEffect(() => {
    fetch('/api/instances/current')
      .then(res => res.ok ? res.json() : null)
      .then(json => {
        const d = json?.data || json;
        if (d && d.name) {
          setCurrentInstance({ id: d.name, name: d.name });
        }
      })
      .catch(err => {
        console.error('Failed to fetch current instance:', err);
        setCurrentInstance({ id: 'study_assistant', name: '学习助手' });
      });
  }, []);

  const handleInstanceSwitch = (instance: { id: string; name: string }) => {
    setCurrentInstance(instance);
  };

  const handleNewInstance = async () => {
    const name = prompt('请输入新实例名称:');
    if (!name) return;

    try {
      const res = await fetch('/api/instances', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name }),
      });
      if (res.ok) {
        window.location.reload();
      }
    } catch (error) {
      console.error('Failed to create instance:', error);
    }
  };

  return (
    <div className="h-screen overflow-hidden neural-grid flex flex-col">
      {/* 顶部栏 */}
      <Header
        currentInstance={currentInstance || undefined}
        onInstanceSwitch={handleInstanceSwitch}
        onNewInstance={handleNewInstance}
        currentPage={currentPage}
        onPageChange={setCurrentPage}
      />

      {/* 主内容区 - ChatDemo和AgentFlow保持挂载，用opacity-0代替invisible确保SSE流不中断 */}
      <main className="flex-1 neural-grid overflow-hidden relative">
        <div className={`absolute inset-0 transition-opacity duration-200 ${currentPage === 'chat' ? 'opacity-100 z-10 pointer-events-auto' : 'opacity-0 z-0 pointer-events-none'}`}>
          <ChatDemo />
        </div>
        <div className={`absolute inset-0 transition-opacity duration-200 ${currentPage === 'agent' ? 'opacity-100 z-10 pointer-events-auto' : 'opacity-0 z-0 pointer-events-none'}`}>
          <AgentFlow />
        </div>
        {currentPage === 'scenario' && <ScenarioDemo />}
        {currentPage === 'stats' && <StatsDashboard />}
        {currentPage === 'memory' && <MemoryList />}
        {currentPage === 'knowledge' && <KnowledgeBase />}
        {currentPage === 'graph' && <MemoryGraph />}
        {currentPage === 'settings' && <Settings currentInstance={currentInstance?.name} />}
        {currentPage === 'sub' && <Sub />}
      </main>
    </div>
  );
}

export default App;
