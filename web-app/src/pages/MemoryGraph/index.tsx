import { useState, useCallback, useMemo, useEffect, useRef } from 'react';
import ForceGraph2D from 'react-force-graph-2d';
import { eventBus } from '../../utils/EventBus';
import { MEMORY_GRAPH_UPDATED } from '../../constants/events';
import { getKeyColor } from '../../mock/memoryGraph';

interface GraphNode {
  id: string;
  key: string;
  tag: string;
  memory: string;
  value_score: number;
  recall_count: number;
  x?: number;
  y?: number;
  vx?: number;
  vy?: number;
  fx?: number;
  fy?: number;
}

interface GraphLink {
  source: string | GraphNode;
  target: string | GraphNode;
  effective_strength: number;
  strength: number;
  reason: string;
}

function getNodeSize(value_score: number): number {
  return 4 + value_score * 8;
}

function getLinkWidth(strength: number): number {
  return 1 + (strength || 0) * 3;
}

export function MemoryGraph() {
  const [nodes, setNodes] = useState<GraphNode[]>([]);
  const [links, setLinks] = useState<GraphLink[]>([]);
  const [keys, setKeys] = useState<Array<{ name: string; label: string }>>([]);
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
  const [selectedKeys, setSelectedKeys] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(true);
  const [graphReady, setGraphReady] = useState(false);
  const graphRef = useRef<any>(null);
  const nodePositionsRef = useRef<Map<string, { x: number; y: number }>>(new Map());
  const isInitialLoadRef = useRef(true);

  const fetchData = useCallback(async () => {
    try {
      const [nodesRes, linksRes, keysRes] = await Promise.all([
        fetch('/api/memory/graph/nodes'),
        fetch('/api/memory/graph/edges'),
        fetch('/api/memory/keys'),
      ]);

      if (nodesRes.ok && linksRes.ok && keysRes.ok) {
        const nodesData = await nodesRes.json();
        const linksData = await linksRes.json();
        const keysData = await keysRes.json();

        const rawNodes = nodesData.data || [];
        const adaptedNodes = rawNodes.map((n: any) => ({
          id: n.fingerprint || n.id,
          key: n.key,
          tag: n.tag,
          memory: n.memory,
          value_score: n.value_score ?? n.weight ?? 0,
          recall_count: n.recall_count ?? 0,
        }));

        const rawLinks = (linksData.data || []).map((l: any) => ({
          source: l.source || l.from_fingerprint,
          target: l.target || l.to_fingerprint,
          strength: l.strength ?? 0.5,
          effective_strength: l.effective_strength ?? l.strength ?? 0.5,
          reason: l.reason || '',
        }));

        const rawKeys = keysData.data || [];
        const adaptedKeys = rawKeys.map((k: any) => ({
          name: k.key || k,
          label: k.label || k.key || k,
        }));

        setNodes(adaptedNodes);
        setLinks(rawLinks);
        setKeys(adaptedKeys);
        setGraphReady(true);
      }
    } catch (err) {
      console.error('Failed to fetch graph data:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
    const unsubscribe = eventBus.on(MEMORY_GRAPH_UPDATED, () => {
      fetchData();
    });
    return () => {
      unsubscribe();
    };
  }, [fetchData]);

  const activeKeys = useMemo(() =>
    selectedKeys.size === 0
      ? new Set(keys.map(k => k.name))
      : selectedKeys,
    [selectedKeys, keys]
  );

  const filteredData = useMemo(() => {
    const nodeMap = new Map(nodes.map(n => [n.id, n]));
    const filteredNodes = nodes.filter(n => activeKeys.has(n.key));
    const filteredNodeIds = new Set(filteredNodes.map(n => n.id));

    const filteredLinks = links.filter(l => {
      const sourceId = typeof l.source === 'string' ? l.source : (l.source as any)?.id;
      const targetId = typeof l.target === 'string' ? l.target : (l.target as any)?.id;
      return sourceId && targetId && filteredNodeIds.has(sourceId) && filteredNodeIds.has(targetId);
    });

    return { nodes: filteredNodes, links: filteredLinks };
  }, [nodes, links, activeKeys]);

  const graphData = useMemo(() => {
    const savedPositions = nodePositionsRef.current;
    const nodesWithPositions = filteredData.nodes.map(n => {
      const saved = savedPositions.get(n.id);
      return saved ? { ...n, x: saved.x, y: saved.y } : { ...n };
    });

    const nodeMap = new Map(nodesWithPositions.map(n => [n.id, n]));
    const linksWithRefs = filteredData.links.map(l => {
      const sourceId = typeof l.source === 'string' ? l.source : (l.source as any)?.id;
      const targetId = typeof l.target === 'string' ? l.target : (l.target as any)?.id;
      return {
        source: nodeMap.get(sourceId) || sourceId,
        target: nodeMap.get(targetId) || targetId,
        effective_strength: l.effective_strength,
        strength: l.strength,
        reason: l.reason,
      };
    });

    return { nodes: nodesWithPositions, links: linksWithRefs };
  }, [filteredData]);

  const handleNodeClick = useCallback((node: GraphNode) => {
    setSelectedNode(node);
  }, []);

  const handleNodeDragEnd = useCallback((node: GraphNode) => {
    if (node.x !== undefined && node.y !== undefined) {
      nodePositionsRef.current.set(node.id, { x: node.x, y: node.y });
    }
  }, []);

  const getRelatedLinks = useCallback((nodeId: string) => {
    return filteredData.links.filter(l => {
      const sourceId = typeof l.source === 'string' ? l.source : (l.source as any)?.id;
      const targetId = typeof l.target === 'string' ? l.target : (l.target as any)?.id;
      return sourceId === nodeId || targetId === nodeId;
    });
  }, [filteredData.links]);

  const getRelatedNodes = useCallback((nodeId: string) => {
    const relatedLinks = getRelatedLinks(nodeId);
    const relatedIds = new Set<string>();
    relatedLinks.forEach(l => {
      const sourceId = typeof l.source === 'string' ? l.source : (l.source as any)?.id;
      const targetId = typeof l.target === 'string' ? l.target : (l.target as any)?.id;
      if (sourceId === nodeId) relatedIds.add(targetId);
      if (targetId === nodeId) relatedIds.add(sourceId);
    });
    return nodes.filter(n => relatedIds.has(n.id));
  }, [getRelatedLinks, nodes]);

  const toggleKey = (keyName: string) => {
    const newKeys = new Set(selectedKeys);
    if (newKeys.has(keyName)) newKeys.delete(keyName);
    else newKeys.add(keyName);
    setSelectedKeys(newKeys);
  };

  const toggleAllKeys = () => {
    setSelectedKeys(selectedKeys.size === 0 ? new Set(keys.map(k => k.name)) : new Set());
  };

  const stats = {
    nodes_count: filteredData.nodes.length,
    links_count: filteredData.links.length,
    avg_connections: filteredData.nodes.length > 0
      ? (filteredData.links.length * 2 / filteredData.nodes.length).toFixed(1)
      : '0',
  };

  const renderDetailModal = () => {
    if (!selectedNode) return null;
    const relatedLinks = getRelatedLinks(selectedNode.id);
    const relatedNodes = getRelatedNodes(selectedNode.id);

    return (
      <div
        className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
        onClick={() => setSelectedNode(null)}
      >
        <div
          className="bg-neural-card/95 backdrop-blur-xl border border-neural-border rounded-2xl w-[480px] max-h-[80vh] overflow-hidden shadow-2xl"
          onClick={e => e.stopPropagation()}
        >
          <div className="px-6 py-5 border-b border-neural-border bg-gradient-to-r from-cyan-500/10 to-purple-500/10">
            <div className="flex items-start justify-between">
              <div>
                <div className="flex items-center gap-2 mb-2">
                  <span
                    className="px-2 py-0.5 rounded text-xs font-medium"
                    style={{
                      backgroundColor: `${getKeyColor(selectedNode.key)}20`,
                      color: getKeyColor(selectedNode.key),
                    }}
                  >
                    {selectedNode.key}
                  </span>
                  <span className="text-slate-500 text-xs">#{selectedNode.id.slice(0, 12)}</span>
                </div>
                <h2 className="text-lg font-bold text-white font-space">{selectedNode.tag}</h2>
              </div>
              <button
                onClick={() => setSelectedNode(null)}
                className="w-8 h-8 rounded-lg bg-neural-bg/50 hover:bg-neural-bg flex items-center justify-center transition-colors"
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <line x1="18" y1="6" x2="6" y2="18" />
                  <line x1="6" y1="6" x2="18" y2="18" />
                </svg>
              </button>
            </div>
          </div>

          <div className="p-6 space-y-5 overflow-y-auto max-h-[calc(80vh-200px)]">
            <div>
              <label className="text-xs text-slate-500 uppercase tracking-wider mb-2 block">记忆内容</label>
              <p className="text-slate-300 leading-relaxed font-chinese bg-neural-bg/50 rounded-lg p-3 text-sm">
                {selectedNode.memory}
              </p>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="bg-neural-bg/50 rounded-lg p-3">
                <label className="text-xs text-slate-500 uppercase tracking-wider mb-1 block">价值分</label>
                <div className="flex items-center gap-2">
                  <span className="text-2xl font-bold text-white font-space">{selectedNode.value_score.toFixed(2)}</span>
                  <div className="flex-1 h-2 bg-neural-bg rounded-full overflow-hidden">
                    <div
                      className="h-full rounded-full transition-all duration-500"
                      style={{
                        width: `${Math.min(selectedNode.value_score * 100, 100)}%`,
                        background: `linear-gradient(90deg, ${getKeyColor(selectedNode.key)}, #22d3ee)`,
                      }}
                    />
                  </div>
                </div>
              </div>
              <div className="bg-neural-bg/50 rounded-lg p-3">
                <label className="text-xs text-slate-500 uppercase tracking-wider mb-1 block">召回次数</label>
                <span className="text-2xl font-bold text-white font-space">{selectedNode.recall_count}</span>
              </div>
            </div>

            {relatedNodes.length > 0 && (
              <div>
                <label className="text-xs text-slate-500 uppercase tracking-wider mb-3 block">
                  关联记忆 ({relatedNodes.length})
                </label>
                <div className="space-y-2">
                  {relatedNodes.slice(0, 5).map(node => {
                    const link = relatedLinks.find(l => {
                      const sourceId = typeof l.source === 'string' ? l.source : (l.source as any)?.id;
                      const targetId = typeof l.target === 'string' ? l.target : (l.target as any)?.id;
                      return (sourceId === selectedNode.id && targetId === node.id) ||
                             (targetId === selectedNode.id && sourceId === node.id);
                    });
                    return (
                      <div
                        key={node.id}
                        className="flex items-start justify-between p-3 bg-neural-bg/50 rounded-lg hover:bg-neural-bg/70 transition-colors cursor-pointer"
                        onClick={() => setSelectedNode(node)}
                      >
                        <div className="flex items-center gap-2 flex-1">
                          <div
                            className="w-2 h-2 rounded-full mt-0.5"
                            style={{ backgroundColor: getKeyColor(node.key) }}
                          />
                          <div>
                            <span className="text-sm text-slate-300 font-chinese">{node.tag}</span>
                            <p className="text-xs text-slate-500 mt-0.5">{link?.reason}</p>
                          </div>
                        </div>
                        <span className="text-xs text-cyan-400 ml-2">
                          {(link?.effective_strength ?? 0).toFixed(2)}
                        </span>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    );
  };

  if (loading) {
    return (
      <div className="h-full neural-grid flex items-center justify-center">
        <div className="text-center">
          <div className="w-16 h-16 border-4 border-cyan-500/30 border-t-cyan-500 rounded-full animate-spin mx-auto mb-4" />
          <p className="text-slate-400">加载图谱数据...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full neural-grid flex flex-col">
      <header className="px-8 py-5 border-b border-neural-border flex-shrink-0">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-cyan-400 to-purple-500 flex items-center justify-center">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="12" cy="12" r="3" />
                <circle cx="19" cy="5" r="2" />
                <circle cx="5" cy="5" r="2" />
                <circle cx="5" cy="19" r="2" />
                <circle cx="19" cy="19" r="2" />
                <line x1="12" y1="9" x2="12" y2="3" />
                <line x1="9.5" y1="10.5" x2="6.5" y2="6.5" />
                <line x1="14.5" y1="10.5" x2="17.5" y2="6.5" />
                <line x1="9.5" y1="13.5" x2="6.5" y2="17.5" />
                <line x1="14.5" y1="13.5" x2="17.5" y2="17.5" />
              </svg>
            </div>
            <div>
              <h1 className="text-xl font-bold text-white font-space">记忆网络图</h1>
              <p className="text-sm text-slate-400 font-chinese">
                {stats.nodes_count}个节点 · {stats.links_count}条边 · 平均连接{stats.avg_connections}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <button onClick={fetchData} className="px-3 py-1.5 rounded-lg text-xs bg-neural-bg/50 hover:bg-neural-bg border border-neural-border transition-colors text-slate-400">
              刷新
            </button>
            <button onClick={toggleAllKeys} className="px-3 py-1.5 rounded-lg text-xs bg-neural-bg/50 hover:bg-neural-bg border border-neural-border transition-colors text-slate-400">
              {selectedKeys.size === 0 ? '全显示' : '重置'}
            </button>
            <div className="flex items-center gap-2 flex-wrap max-w-[400px]">
              {keys.map(key => (
                <button
                  key={key.name}
                  onClick={() => toggleKey(key.name)}
                  className={`px-2.5 py-1 rounded-lg text-xs font-medium transition-all ${
                    activeKeys.has(key.name) ? 'ring-1 ring-offset-1 ring-offset-transparent' : 'opacity-40 hover:opacity-70'
                  }`}
                  style={
                    activeKeys.has(key.name)
                      ? { backgroundColor: `${getKeyColor(key.name)}20`, color: getKeyColor(key.name) }
                      : { backgroundColor: 'rgba(100,116,139,0.2)', color: '#94a3b8' }
                  }
                >
                  {key.label}
                </button>
              ))}
            </div>
          </div>
        </div>
      </header>

      <main className="flex-1 relative overflow-hidden">
        <div className="absolute top-4 left-4 z-10 bg-neural-card/80 backdrop-blur-lg border border-neural-border rounded-xl p-4">
          <h3 className="text-xs text-slate-400 uppercase tracking-wider mb-3">图例</h3>
          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <div className="w-3 h-3 rounded-full bg-cyan-400" />
              <span className="text-xs text-slate-300">节点大小 = 价值分</span>
            </div>
            <div className="flex items-center gap-2">
              <div className="w-0.5 h-4 bg-slate-400" />
              <span className="text-xs text-slate-300">边粗细 = 关联强度</span>
            </div>
            <div className="flex items-center gap-2">
              <div className="w-3 h-3 rounded-full" style={{ backgroundColor: getKeyColor('study') }} />
              <span className="text-xs text-slate-300">节点颜色 = Key分类</span>
            </div>
          </div>
        </div>

        <div className="absolute top-4 right-4 z-10 bg-neural-card/80 backdrop-blur-lg border border-neural-border rounded-xl px-4 py-3">
          <p className="text-xs text-slate-400 font-chinese">
            <span className="text-cyan-400">拖拽:</span> 移动节点位置 · <span className="text-cyan-400">滚轮:</span> 缩放 · <span className="text-cyan-400">点击:</span> 查看详情
          </p>
        </div>

        {graphReady && filteredData.nodes.length > 0 ? (
          <ForceGraph2D
            ref={graphRef}
            graphData={graphData}
            nodeId="id"
            nodeLabel={(node: any) => node.tag}
            nodeVal={(node: any) => getNodeSize(node.value_score)}
            nodeColor={(node: any) => getKeyColor(node.key)}
            linkWidth={(link: any) => getLinkWidth(link.effective_strength)}
            linkColor={() => 'rgba(100, 116, 139, 0.4)'}
            nodeCanvasObject={(node: any, ctx: CanvasRenderingContext2D, globalScale: number) => {
              const label = node.tag;
              const nodeSize = getNodeSize(node.value_score);
              const fontSize = Math.max(8 / globalScale, 2.5);
              const keyColor = getKeyColor(node.key);
              const x = Number.isFinite(node.x) ? node.x : 0;
              const y = Number.isFinite(node.y) ? node.y : 0;

              const gradient = ctx.createRadialGradient(x, y, nodeSize, x, y, nodeSize + 14);
              gradient.addColorStop(0, keyColor + '50');
              gradient.addColorStop(1, keyColor + '00');
              ctx.beginPath();
              ctx.arc(x, y, nodeSize + 14, 0, 2 * Math.PI);
              ctx.fillStyle = gradient;
              ctx.fill();

              ctx.beginPath();
              ctx.arc(x, y, nodeSize, 0, 2 * Math.PI);
              ctx.fillStyle = keyColor;
              ctx.fill();

              ctx.font = `bold ${fontSize}px Space_Mono, monospace`;
              ctx.textAlign = 'center';
              ctx.textBaseline = 'middle';
              ctx.fillStyle = 'rgba(255,255,255,0.85)';
              ctx.shadowColor = 'rgba(0,0,0,0.9)';
              ctx.shadowBlur = 4;
              ctx.fillText(label, x, y + nodeSize + fontSize + 2);
            }}
            nodePointerAreaPaint={(node: any, color: string, ctx: CanvasRenderingContext2D) => {
              const nodeSize = getNodeSize(node.value_score);
              ctx.fillStyle = color;
              ctx.beginPath();
              ctx.arc(node.x, node.y, nodeSize + 4, 0, 2 * Math.PI);
              ctx.fill();
            }}
            onNodeClick={handleNodeClick}
            onNodeDragEnd={handleNodeDragEnd}
            d3VelocityDecay={0.4}
            cooldownTicks={isInitialLoadRef.current ? 200 : 50}
            warmupTicks={isInitialLoadRef.current ? 100 : 0}
            backgroundColor="transparent"
            enableNodeDrag={true}
            enableZoomInteraction={true}
            enablePanInteraction={true}
          />
        ) : graphReady && filteredData.nodes.length === 0 ? (
          <div className="flex items-center justify-center h-full">
            <div className="text-center">
              <p className="text-slate-400 font-chinese">没有选中的Key</p>
              <p className="text-sm text-slate-500">请至少选择一个Key来显示网络图</p>
            </div>
          </div>
        ) : null}
      </main>

      <footer className="px-8 py-3 border-t border-neural-border bg-neural-card/50 flex-shrink-0">
        <div className="flex items-center justify-center gap-8">
          <div className="flex items-center gap-2">
            <span className="text-xs text-slate-500 uppercase tracking-wider">节点数</span>
            <span className="text-lg font-bold text-white font-space">{stats.nodes_count}</span>
          </div>
          <div className="w-px h-4 bg-neural-border" />
          <div className="flex items-center gap-2">
            <span className="text-xs text-slate-500 uppercase tracking-wider">边数</span>
            <span className="text-lg font-bold text-white font-space">{stats.links_count}</span>
          </div>
          <div className="w-px h-4 bg-neural-border" />
          <div className="flex items-center gap-2">
            <span className="text-xs text-slate-500 uppercase tracking-wider">平均连接</span>
            <span className="text-lg font-bold text-cyan-400 font-space">{stats.avg_connections}</span>
          </div>
        </div>
      </footer>

      {renderDetailModal()}
    </div>
  );
}
