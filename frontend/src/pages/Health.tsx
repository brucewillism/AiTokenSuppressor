import { useEffect, useState } from 'react';
import { StatusBadge, LoadingSpinner } from '../components/StatCard';
import ApiConnectionHint from '../components/ApiConnectionHint';
import { api, HealthStatus } from '../services/api';

type ServiceInfo = { status: string; latency_ms?: number | null; details?: Record<string, unknown> };

function normalizeService(info: unknown): ServiceInfo {
  if (typeof info === 'string') {
    return { status: info };
  }
  if (info && typeof info === 'object') {
    const row = info as Record<string, unknown>;
    return {
      status: String(row.status ?? 'unknown'),
      latency_ms: typeof row.latency_ms === 'number' ? row.latency_ms : null,
      details: row.details as Record<string, unknown> | undefined,
    };
  }
  return { status: 'unknown' };
}

export default function Health() {
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const check = async () => {
      try {
        const data = await api.getHealth();
        setHealth(data);
        setError(null);
      } catch (err) {
        setHealth(null);
        setError(err instanceof Error ? err.message : 'Falha ao carregar health');
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
        {health && (
          <p className="text-gray-500 text-sm mt-2">
            Geral: <StatusBadge status={health.status === 'healthy' ? 'healthy' : 'degraded'} />
            {' · '}
            <span className="font-mono text-xs">/api/health/full</span>
          </p>
        )}
      </div>

      {Object.keys(services).length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {Object.entries(services).map(([name, raw]) => {
            const info = normalizeService(raw);
            return (
              <div key={name} className="bg-dark-800 rounded-xl p-6 border border-gray-800">
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-lg font-semibold text-white capitalize">{name}</h3>
                  <StatusBadge status={info.status === 'degraded' ? 'unhealthy' : info.status} />
                </div>
                {info.latency_ms != null && (
                  <p className="text-gray-400 text-sm">Latência: {info.latency_ms.toFixed(1)}ms</p>
                )}
                {info.details?.error != null ? (
                  <p className="text-red-400/80 text-xs mt-2 break-all">{String(info.details.error)}</p>
                ) : null}
              </div>
            );
          })}
        </div>
      )}

      {!health && <ApiConnectionHint error={error ?? 'API indisponível'} />}

      <p className="text-gray-600 text-xs">
        Probe JSON (monitoramento):{' '}
        <a href="/health/live" className="text-primary-400 hover:underline font-mono">
          /health/live
        </a>
      </p>
    </div>
  );
}
