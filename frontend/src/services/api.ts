const API_BASE = import.meta.env.VITE_API_URL || '/api';
const API_KEY = import.meta.env.VITE_API_KEY || 'ats-dev-api-key-change-in-production';

export { API_BASE, API_KEY };

export interface ApiDisplayInfo {
  url: string;
  host: string;
  port: string;
  directHealthUrl: string | null;
}

/** URL/host/porta exibidos na UI — espelha VITE_API_URL ou proxy /api no mesmo origin. */
export function getApiDisplayInfo(): ApiDisplayInfo {
  const directHealthUrl = getDirectHealthUrl();
  const base = API_BASE.trim();

  if (base.startsWith('http://') || base.startsWith('https://')) {
    try {
      const parsed = new URL(base);
      const port =
        parsed.port ||
        (parsed.protocol === 'https:' ? '443' : '80');
      return {
        url: base.replace(/\/$/, ''),
        host: parsed.hostname,
        port,
        directHealthUrl,
      };
    } catch {
      return { url: base, host: base, port: '—', directHealthUrl };
    }
  }

  const path = base.startsWith('/') ? base : `/${base}`;
  if (typeof window !== 'undefined') {
    const { origin, hostname, port, protocol } = window.location;
    const resolvedPort = port || (protocol === 'https:' ? '443' : '80');
    return {
      url: `${origin}${path}`,
      host: hostname,
      port: resolvedPort,
      directHealthUrl,
    };
  }

  return { url: path, host: 'localhost', port: '8000', directHealthUrl };
}

function getDirectHealthUrl(): string | null {
  const configured = import.meta.env.VITE_API_DIRECT_URL?.trim();
  if (configured) {
    return configured.replace(/\/$/, '') + '/health';
  }
  return null;
}

const REQUEST_TIMEOUT_MS = 180_000;

async function request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);

  let response: Response;
  try {
    response = await fetch(`${API_BASE}${endpoint}`, {
      ...options,
      signal: controller.signal,
      headers: {
        'Content-Type': 'application/json',
        'X-API-Key': API_KEY,
        ...options.headers,
      },
    });
  } catch (err) {
    if (err instanceof Error && err.name === 'AbortError') {
      throw new Error(
        'Tempo esgotado (3 min). Use estratégia code-focused ou desative Ollama; ultra/balanced chamam o LLM local.'
      );
    }
    throw err;
  } finally {
    clearTimeout(timeoutId);
  }

  if (!response.ok) {
    if (response.status === 502 || response.status === 503) {
      throw new Error('Bad Gateway');
    }
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
  compress: (
    messages: Array<{ role: string; content: string }>,
    strategy = 'balanced',
    options?: { checkSemanticLoss?: boolean; useOllama?: boolean },
  ) =>
    request('/compress', {
      method: 'POST',
      body: JSON.stringify({
        messages,
        strategy,
        ...(options?.checkSemanticLoss !== undefined
          ? { check_semantic_loss: options.checkSemanticLoss }
          : {}),
        ...(options?.useOllama !== undefined ? { use_ollama: options.useOllama } : {}),
      }),
    }),
  optimize: (
    messages: Array<{ role: string; content: string }>,
    strategy = 'balanced',
    options?: { useMemory?: boolean; useRag?: boolean; checkSemanticLoss?: boolean },
  ) =>
    request('/optimize', {
      method: 'POST',
      body: JSON.stringify({
        messages,
        strategy,
        use_memory: options?.useMemory ?? false,
        use_rag: options?.useRag ?? false,
        check_semantic_loss: options?.checkSemanticLoss ?? false,
      }),
    }),
};
