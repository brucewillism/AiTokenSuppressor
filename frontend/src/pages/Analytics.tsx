import { useState } from 'react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from 'recharts';
import { advancedApi, HeatmapSegment, BenchmarkResult } from '../services/advancedApi';

const TYPE_COLORS: Record<string, string> = {
  code: '#6366f1', chat: '#8b5cf6', logs: '#f59e0b', json: '#10b981',
  markdown: '#3b82f6', stacktrace: '#ef4444', documentation: '#06b6d4',
  mixed: '#a78bfa', unknown: '#6b7280',
};

export default function Analytics() {
  const [input, setInput] = useState(
    'Implement a FastAPI service with PostgreSQL, Redis cache, JWT auth, and Docker deployment.\n\n```python\ndef hello():\n    return {"status": "ok"}\n```'
  );
  const [heatmap, setHeatmap] = useState<HeatmapSegment[]>([]);
  const [hotspots, setHotspots] = useState<string[]>([]);
  const [benchmark, setBenchmark] = useState<BenchmarkResult[]>([]);
  const [bestStrategy, setBestStrategy] = useState('');
  const [loading, setLoading] = useState(false);
  const [totalTokens, setTotalTokens] = useState(0);

  const messages = [
    { role: 'system', content: 'You are a senior backend engineer.' },
    { role: 'user', content: input },
  ];

  const runAnalysis = async () => {
    setLoading(true);
    try {
      const [hm, bm] = await Promise.all([
        advancedApi.heatmap(messages),
        advancedApi.benchmark(messages),
      ]);
      setHeatmap(hm.segments);
      setHotspots(hm.hotspots);
      setTotalTokens(hm.total_tokens);
      setBenchmark(bm.results);
      setBestStrategy(bm.best_strategy);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const heatmapChart = heatmap.map((s) => ({
    name: s.label.slice(0, 20),
    tokens: s.tokens,
    type: s.content_type,
    compressible: s.compressible,
  }));

  return (
    <div className="space-y-8">
      <div>
        <h2 className="text-2xl font-bold text-white">Analytics Avançado</h2>
        <p className="text-gray-400 mt-1">Token heatmap, benchmark de estratégias e semantic loss</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-1 space-y-4">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            rows={8}
            className="w-full bg-dark-800 border border-gray-700 rounded-lg px-4 py-3 text-white text-sm resize-none"
          />
          <button
            onClick={runAnalysis}
            disabled={loading}
            className="w-full bg-primary-600 hover:bg-primary-700 disabled:opacity-50 text-white py-2.5 rounded-lg font-medium"
          >
            {loading ? 'Analisando...' : 'Executar Análise'}
          </button>
          {bestStrategy && (
            <div className="bg-green-500/10 border border-green-500/20 rounded-lg p-4">
              <p className="text-green-400 text-sm font-medium">Melhor estratégia</p>
              <p className="text-white text-lg font-bold mt-1">{bestStrategy}</p>
            </div>
          )}
        </div>

        <div className="lg:col-span-2 space-y-6">
          {heatmap.length > 0 && (
            <div className="bg-dark-800 rounded-xl p-6 border border-gray-800">
              <h3 className="text-lg font-semibold text-white mb-2">
                Token Heatmap ({totalTokens.toLocaleString()} tokens)
              </h3>
              <ResponsiveContainer width="100%" height={250}>
                <BarChart data={heatmapChart} layout="vertical">
                  <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                  <XAxis type="number" stroke="#9ca3af" />
                  <YAxis type="category" dataKey="name" stroke="#9ca3af" width={120} tick={{ fontSize: 11 }} />
                  <Tooltip contentStyle={{ backgroundColor: '#1e1e2e', border: '1px solid #374151' }} />
                  <Bar dataKey="tokens" radius={[0, 4, 4, 0]}>
                    {heatmapChart.map((entry, i) => (
                      <Cell key={i} fill={TYPE_COLORS[entry.type] || '#6366f1'} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
              {hotspots.length > 0 && (
                <div className="mt-4 flex flex-wrap gap-2">
                  {hotspots.map((h) => (
                    <span key={h} className="text-xs bg-red-500/10 text-red-400 px-2 py-1 rounded border border-red-500/20">
                      {h}
                    </span>
                  ))}
                </div>
              )}
            </div>
          )}

          {benchmark.length > 0 && (
            <div className="bg-dark-800 rounded-xl border border-gray-800 overflow-hidden">
              <div className="p-4 border-b border-gray-800">
                <h3 className="text-lg font-semibold text-white">Benchmark de Estratégias</h3>
              </div>
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-gray-400 border-b border-gray-800">
                    <th className="text-left p-3">Estratégia</th>
                    <th className="text-right p-3">Economia</th>
                    <th className="text-right p-3">Semantic Loss</th>
                    <th className="text-right p-3">Latência</th>
                    <th className="text-center p-3">Qualidade</th>
                  </tr>
                </thead>
                <tbody>
                  {benchmark.map((b) => (
                    <tr key={b.strategy} className="border-b border-gray-800/50 hover:bg-dark-900/50">
                      <td className="p-3 text-white font-medium">{b.strategy}</td>
                      <td className="p-3 text-green-400 text-right">{b.savings_percent.toFixed(1)}%</td>
                      <td className="p-3 text-right">
                        <span className={b.semantic_loss_score > 0.35 ? 'text-red-400' : 'text-green-400'}>
                          {(b.semantic_loss_score * 100).toFixed(1)}%
                        </span>
                      </td>
                      <td className="p-3 text-gray-400 text-right">{b.latency_ms.toFixed(0)}ms</td>
                      <td className="p-3 text-center">
                        {b.quality_preserved ? (
                          <span className="text-green-400">OK</span>
                        ) : (
                          <span className="text-red-400">!</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
