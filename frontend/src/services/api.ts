const API_BASE = import.meta.env.VITE_API_URL || '/api';
const API_KEY = import.meta.env.VITE_API_KEY || 'ats-dev-api-key-change-in-production';

async function request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_BASE}${endpoint}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      'X-API-Key': API_KEY,
      ...options.headers,
    },
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: response.statusText }));
    throw new Error(error.message || `HTTP ${response.status}`);
  }

  return response.json();
}

export interface Stats {
  total_requests: number;
  total_tokens_saved: number;
  total_cost_saved_usd: number;
  average_compression_ratio: number;
  average_latency_ms: number;
  cache_hit_rate: number;
  requests_by_strategy: Record<string, number>;
  requests_by_model: Record<string, number>;
  recent_requests: Array<{
    id: string;
    endpoint: string;
    strategy: string;
    tokens_before: number;
    tokens_after: number;
    tokens_saved: number;
    compression_ratio: number;
    latency_ms: number;
    cache_hit: boolean;
    created_at: string;
  }>;
}

export interface HealthStatus {
  status: string;
  services: Record<string, { status: string; latency_ms?: number }>;
}

export const api = {
  getStats: (days = 7) => request<Stats>(`/stats?days=${days}`),
  getHealth: () => request<HealthStatus>('/health/full'),
  compress: (messages: Array<{ role: string; content: string }>, strategy = 'balanced') =>
    request('/compress', {
      method: 'POST',
      body: JSON.stringify({ messages, strategy }),
    }),
  optimize: (messages: Array<{ role: string; content: string }>, strategy = 'balanced') =>
    request('/optimize', {
      method: 'POST',
      body: JSON.stringify({ messages, strategy, use_memory: true }),
    }),
};
