import { api, API_BASE, API_KEY } from './api';

export interface HeatmapSegment {
  index: number;
  role: string;
  content_type: string;
  tokens: number;
  percent: number;
  label: string;
  compressible: boolean;
  is_critical?: boolean;
  relevance_score?: number;
}

export interface HeatmapData {
  total_tokens: number;
  segments: HeatmapSegment[];
  hotspots: string[];
}

export interface BenchmarkResult {
  strategy: string;
  tokens_before: number;
  tokens_after: number;
  compression_ratio: number;
  savings_percent: number;
  semantic_loss_score: number;
  latency_ms: number;
  quality_preserved: boolean;
  balance_score: number;
}

async function advancedRequest<T>(endpoint: string, body: unknown): Promise<T> {
  const response = await fetch(`${API_BASE}${endpoint}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-API-Key': API_KEY },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    if (response.status === 502 || response.status === 503) {
      throw new Error('Bad Gateway');
    }
    throw new Error(`HTTP ${response.status}`);
  }
  return response.json();
}

export const advancedApi = {
  heatmap: (messages: Array<{ role: string; content: string }>, targetModel = 'claude-3-5-sonnet') =>
    advancedRequest<HeatmapData>('/advanced/heatmap', { messages, target_model: targetModel }),

  benchmark: (messages: Array<{ role: string; content: string }>, targetModel = 'claude-3-5-sonnet') =>
    advancedRequest<{ results: BenchmarkResult[]; best_strategy: string; best_balance_score: number }>(
      '/advanced/benchmark',
      { messages, target_model: targetModel },
    ),

  graphQuery: (query: string, userId = 'default') =>
    advancedRequest<{
      nodes: Array<{ id: string; label: string; entity_type: string; weight: number }>;
      edges: Array<{ source: string; target: string; relationship: string }>;
      context_summary: string;
    }>('/advanced/graph/query', { query, user_id: userId }),
};

export { api };
