import { useEffect, useState } from 'react';
import { StatusBadge, LoadingSpinner } from '../components/StatCard';
import { api, HealthStatus } from '../services/api';

export default function Health() {
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const check = async () => {
      try {
        const data = await api.getHealth();
        setHealth(data);
      } catch {
        setHealth(null);
      } finally {
        setLoading(false);
      }
    };
    check();
    const interval = setInterval(check, 15000);
    return () => clearInterval(interval);
  }, []);

  if (loading) return <LoadingSpinner />;

  const services = health?.services ?? {};

  return (
    <div className="space-y-8">
      <div>
        <h2 className="text-2xl font-bold text-white">Health Checks</h2>
        <p className="text-gray-400 mt-1">Status dos serviços da infraestrutura</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {Object.entries(services).map(([name, info]) => (
          <div key={name} className="bg-dark-800 rounded-xl p-6 border border-gray-800">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold text-white capitalize">{name}</h3>
              <StatusBadge status={info.status} />
            </div>
            {'latency_ms' in info && info.latency_ms !== undefined && (
              <p className="text-gray-400 text-sm">Latência: {info.latency_ms.toFixed(1)}ms</p>
            )}
          </div>
        ))}
      </div>

      {!health && (
        <div className="text-center py-12 bg-dark-800 rounded-xl border border-red-500/20">
          <p className="text-red-400">API indisponível</p>
        </div>
      )}
    </div>
  );
}
