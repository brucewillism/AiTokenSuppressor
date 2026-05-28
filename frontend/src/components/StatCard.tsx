import { ReactNode } from 'react';
import { Zap, Activity, Database, Cpu, BarChart3 } from 'lucide-react';

interface StatCardProps {
  title: string;
  value: string | number;
  subtitle?: string;
  icon: ReactNode;
  trend?: string;
  color?: string;
}

export function StatCard({ title, value, subtitle, icon, trend, color = 'primary' }: StatCardProps) {
  return (
    <div className="bg-dark-800 rounded-xl p-6 border border-gray-800 hover:border-primary-500/30 transition-all">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-gray-400 text-sm font-medium">{title}</p>
          <p className="text-3xl font-bold text-white mt-2">{value}</p>
          {subtitle && <p className="text-gray-500 text-xs mt-1">{subtitle}</p>}
          {trend && (
            <p className="text-green-400 text-xs mt-2 font-medium">{trend}</p>
          )}
        </div>
        <div className={`p-3 rounded-lg bg-${color}-500/10 text-primary-500`}>
          {icon}
        </div>
      </div>
    </div>
  );
}

export function LoadingSpinner() {
  return (
    <div className="flex items-center justify-center h-64">
      <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary-500" />
    </div>
  );
}

export function StatusBadge({ status }: { status: string }) {
  const isHealthy = status === 'healthy' || status === 'ok';
  const isDegraded = status === 'degraded';
  return (
    <span
      className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${
        isHealthy
          ? 'bg-green-500/10 text-green-400 border border-green-500/20'
          : isDegraded
            ? 'bg-amber-500/10 text-amber-400 border border-amber-500/20'
            : 'bg-red-500/10 text-red-400 border border-red-500/20'
      }`}
    >
      <span
        className={`w-1.5 h-1.5 rounded-full mr-1.5 ${
          isHealthy ? 'bg-green-400' : isDegraded ? 'bg-amber-400' : 'bg-red-400'
        }`}
      />
      {status}
    </span>
  );
}

export { Zap, Activity, Database, Cpu, BarChart3 };
