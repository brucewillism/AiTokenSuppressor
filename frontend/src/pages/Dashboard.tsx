import { useEffect, useState } from 'react';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, LineChart, Line,
} from 'recharts';
import { StatCard, LoadingSpinner, Zap, Activity, Database, BarChart3 } from '../components/StatCard';
import ApiConnectionHint from '../components/ApiConnectionHint';
import { api, Stats } from '../services/api';

const COLORS = ['#6366f1', '#8b5cf6', '#a78bfa', '#c4b5fd', '#818cf8', '#4f46e5'];

export default function Dashboard() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchStats = async () => {
      try {
        const data = await api.getStats(7);
        setStats(data);
        setError(null);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load stats');
      } finally {
        setLoading(false);
      }
    };

    fetchStats();
    const interval = setInterval(fetchStats, 10000);
    return () => clearInterval(interval);
  }, []);

  if (loading) return <LoadingSpinner />;
  if (error) return <ApiConnectionHint error={error} />;
  if (!stats) return null;

  const strategyData = Object.entries(stats.requests_by_strategy).map(([name, value]) => ({
    name, value,
  }));

  const savingsData = stats.recent_requests.slice(0, 10).map((r) => ({
    time: new Date(r.created_at).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' }),
    saved: r.tokens_saved,
    latency: r.latency_ms,
  }));

  const compressionPercent = ((1 - stats.average_compression_ratio) * 100).toFixed(1);

  return (
    <div className="space-y-8">
      <div>
        <h2 className="text-2xl font-bold text-white">Dashboard</h2>
        <p className="text-gray-400 mt-1">Monitoramento em tempo real da otimização de tokens</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <StatCard
          title="Tokens Economizados"
          value={stats.total_tokens_saved.toLocaleString('pt-BR')}
          subtitle="Últimos 7 dias"
          icon={<Zap className="w-6 h-6" />}
          trend={`${compressionPercent}% compressão média`}
        />
        <StatCard
          title="Custo Economizado"
          value={`$${stats.total_cost_saved_usd.toFixed(2)}`}
          subtitle="Estimativa USD"
          icon={<BarChart3 className="w-6 h-6" />}
        />
        <StatCard
          title="Requests Otimizadas"
          value={stats.total_requests.toLocaleString('pt-BR')}
          subtitle={`Cache hit: ${stats.cache_hit_rate.toFixed(1)}%`}
          icon={<Activity className="w-6 h-6" />}
        />
        <StatCard
          title="Latência Média"
          value={`${stats.average_latency_ms.toFixed(0)}ms`}
          subtitle="Por request"
          icon={<Database className="w-6 h-6" />}
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-dark-800 rounded-xl p-6 border border-gray-800">
          <h3 className="text-lg font-semibold text-white mb-4">Tokens Economizados (Recentes)</h3>
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={savingsData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
              <XAxis dataKey="time" stroke="#9ca3af" fontSize={12} />
              <YAxis stroke="#9ca3af" fontSize={12} />
              <Tooltip
                contentStyle={{ backgroundColor: '#1e1e2e', border: '1px solid #374151', borderRadius: '8px' }}
                labelStyle={{ color: '#fff' }}
              />
              <Bar dataKey="saved" fill="#6366f1" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="bg-dark-800 rounded-xl p-6 border border-gray-800">
          <h3 className="text-lg font-semibold text-white mb-4">Estratégias de Compressão</h3>
          {strategyData.length > 0 ? (
            <ResponsiveContainer width="100%" height={300}>
              <PieChart>
                <Pie
                  data={strategyData}
                  cx="50%"
                  cy="50%"
                  innerRadius={60}
                  outerRadius={100}
                  paddingAngle={5}
                  dataKey="value"
                  label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
                >
                  {strategyData.map((_, index) => (
                    <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip
                  contentStyle={{ backgroundColor: '#1e1e2e', border: '1px solid #374151', borderRadius: '8px' }}
                />
              </PieChart>
            </ResponsiveContainer>
          ) : (
            <p className="text-gray-500 text-center py-20">Nenhum dado ainda</p>
          )}
        </div>
      </div>

      <div className="bg-dark-800 rounded-xl p-6 border border-gray-800">
        <h3 className="text-lg font-semibold text-white mb-4">Latência por Request</h3>
        <ResponsiveContainer width="100%" height={200}>
          <LineChart data={savingsData}>
            <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
            <XAxis dataKey="time" stroke="#9ca3af" fontSize={12} />
            <YAxis stroke="#9ca3af" fontSize={12} unit="ms" />
            <Tooltip
              contentStyle={{ backgroundColor: '#1e1e2e', border: '1px solid #374151', borderRadius: '8px' }}
            />
            <Line type="monotone" dataKey="latency" stroke="#8b5cf6" strokeWidth={2} dot={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>

      <div className="bg-dark-800 rounded-xl border border-gray-800 overflow-hidden">
        <div className="p-6 border-b border-gray-800">
          <h3 className="text-lg font-semibold text-white">Requests Recentes</h3>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="text-gray-400 text-sm border-b border-gray-800">
                <th className="text-left p-4 font-medium">Endpoint</th>
                <th className="text-left p-4 font-medium">Estratégia</th>
                <th className="text-right p-4 font-medium">Antes</th>
                <th className="text-right p-4 font-medium">Depois</th>
                <th className="text-right p-4 font-medium">Economia</th>
                <th className="text-right p-4 font-medium">Latência</th>
                <th className="text-center p-4 font-medium">Cache</th>
              </tr>
            </thead>
            <tbody>
              {stats.recent_requests.map((req) => (
                <tr key={req.id} className="border-b border-gray-800/50 hover:bg-dark-900/50">
                  <td className="p-4 text-white text-sm">{req.endpoint}</td>
                  <td className="p-4 text-gray-300 text-sm">{req.strategy}</td>
                  <td className="p-4 text-gray-400 text-sm text-right">{req.tokens_before.toLocaleString()}</td>
                  <td className="p-4 text-gray-400 text-sm text-right">{req.tokens_after.toLocaleString()}</td>
                  <td className="p-4 text-green-400 text-sm text-right font-medium">
                    -{req.tokens_saved.toLocaleString()}
                  </td>
                  <td className="p-4 text-gray-400 text-sm text-right">{req.latency_ms.toFixed(0)}ms</td>
                  <td className="p-4 text-center">
                    {req.cache_hit ? (
                      <span className="text-green-400 text-xs">HIT</span>
                    ) : (
                      <span className="text-gray-600 text-xs">MISS</span>
                    )}
                  </td>
                </tr>
              ))}
              {stats.recent_requests.length === 0 && (
                <tr>
                  <td colSpan={7} className="p-8 text-center text-gray-500">
                    Nenhum request registrado ainda. Use a API para começar.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
