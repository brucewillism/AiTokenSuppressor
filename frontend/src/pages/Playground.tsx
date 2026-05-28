import { useEffect, useRef, useState } from 'react';
import { api } from '../services/api';

const STRATEGIES = ['fast', 'code-focused', 'balanced', 'aggressive', 'chat-focused', 'semantic', 'ultra'];
const SLOW_STRATEGIES = new Set(['ultra', 'balanced', 'aggressive', 'semantic', 'chat-focused']);

function formatElapsed(ms: number): string {
  const sec = Math.floor(ms / 1000);
  if (sec < 60) return `${sec}s`;
  return `${Math.floor(sec / 60)}m ${sec % 60}s`;
}

export default function Playground() {
  const [input, setInput] = useState('You are a helpful assistant.\n\nUser: Explain how to build a REST API with FastAPI including authentication, database models, and error handling. Provide detailed examples with code.');
  const [strategy, setStrategy] = useState('fast');
  const [result, setResult] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fastMode, setFastMode] = useState(true);
  const [elapsedMs, setElapsedMs] = useState(0);
  const abortRef = useRef<AbortController | null>(null);

  const slowRun = !fastMode && SLOW_STRATEGIES.has(strategy);

  useEffect(() => {
    if (!loading) {
      setElapsedMs(0);
      return;
    }
    const start = Date.now();
    const id = window.setInterval(() => setElapsedMs(Date.now() - start), 1000);
    return () => window.clearInterval(id);
  }, [loading]);

  const buildMessages = () => [
    { role: 'system', content: 'You are a helpful assistant.' },
    { role: 'user', content: input },
  ];

  const runAction = async (action: 'compress' | 'optimize') => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setLoading(true);
    setError(null);
    const messages = buildMessages();
    const opts = {
      checkSemanticLoss: fastMode ? false : undefined,
      useOllama: fastMode ? false : undefined,
      signal: controller.signal,
    };

    try {
      const data =
        action === 'compress'
          ? await api.compress(messages, strategy, opts)
          : await api.optimize(messages, strategy, {
              ...opts,
              useMemory: fastMode ? false : true,
              useRag: false,
            });
      setResult(data as Record<string, unknown>);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erro na requisição');
    } finally {
      setLoading(false);
      abortRef.current = null;
    }
  };

  const handleCancel = () => {
    abortRef.current?.abort();
  };

  return (
    <div className="space-y-8">
      <div>
        <h2 className="text-2xl font-bold text-white">Playground</h2>
        <p className="text-gray-400 mt-1">Teste compressão e otimização de prompts em tempo real</p>
        <p className="text-gray-500 text-xs mt-2 max-w-2xl">
          Use <span className="text-primary-400">fast</span> ou{' '}
          <span className="text-primary-400">code-focused</span> para respostas em segundos.
          <span className="text-gray-400"> ultra</span> /{' '}
          <span className="text-gray-400">balanced</span> com Ollama podem levar vários minutos na VPS.
          Mantenha <span className="text-primary-400">Modo rápido</span> ativo no dia a dia.
        </p>
      </div>

      {slowRun && (
        <div className="bg-amber-500/10 border border-amber-500/30 rounded-lg p-4 text-amber-200 text-sm">
          <strong>Atenção:</strong> estratégia <em>{strategy}</em> com Modo rápido desligado usa Ollama na
          VPS e pode demorar vários minutos. Ative Modo rápido ou troque para{' '}
          <button
            type="button"
            className="underline text-primary-300"
            onClick={() => setStrategy('code-focused')}
          >
            code-focused
          </button>
          .
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-2">Estratégia</label>
            <select
              value={strategy}
              onChange={(e) => setStrategy(e.target.value)}
              disabled={loading}
              className="w-full bg-dark-800 border border-gray-700 rounded-lg px-4 py-2 text-white focus:ring-2 focus:ring-primary-500 focus:border-transparent disabled:opacity-50"
            >
              {STRATEGIES.map((s) => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
          </div>

          <label className="flex items-center gap-2 text-sm text-gray-400 cursor-pointer">
            <input
              type="checkbox"
              checked={fastMode}
              onChange={(e) => setFastMode(e.target.checked)}
              disabled={loading}
              className="rounded border-gray-600 bg-dark-800 text-primary-500 focus:ring-primary-500"
            />
            Modo rápido (sem Ollama para métrica semântica / memória)
          </label>

          <div>
            <label className="block text-sm font-medium text-gray-300 mb-2">Prompt</label>
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              disabled={loading}
              rows={12}
              className="w-full bg-dark-800 border border-gray-700 rounded-lg px-4 py-3 text-white font-mono text-sm focus:ring-2 focus:ring-primary-500 focus:border-transparent resize-none disabled:opacity-50"
            />
          </div>

          <div className="flex gap-3">
            <button
              onClick={() => runAction('compress')}
              disabled={loading}
              className="flex-1 bg-primary-600 hover:bg-primary-700 disabled:opacity-50 text-white font-medium py-2.5 px-4 rounded-lg transition-colors"
            >
              {loading ? `Processando… ${formatElapsed(elapsedMs)}` : 'Comprimir'}
            </button>
            <button
              onClick={() => runAction('optimize')}
              disabled={loading}
              className="flex-1 bg-purple-600 hover:bg-purple-700 disabled:opacity-50 text-white font-medium py-2.5 px-4 rounded-lg transition-colors"
            >
              {loading ? `Processando… ${formatElapsed(elapsedMs)}` : 'Otimizar Completo'}
            </button>
            {loading && (
              <button
                type="button"
                onClick={handleCancel}
                className="px-4 py-2.5 rounded-lg border border-gray-600 text-gray-300 hover:bg-dark-700 text-sm"
              >
                Cancelar
              </button>
            )}
          </div>

          {error && (
            <div className="bg-red-500/10 border border-red-500/20 rounded-lg p-4 text-red-400 text-sm">
              {error}
            </div>
          )}
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-300 mb-2">Resultado</label>
          {result ? (
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-3">
                <div className="bg-dark-800 rounded-lg p-4 border border-gray-800">
                  <p className="text-gray-400 text-xs">Tokens Antes</p>
                  <p className="text-2xl font-bold text-white">{String(result.tokens_before)}</p>
                </div>
                <div className="bg-dark-800 rounded-lg p-4 border border-gray-800">
                  <p className="text-gray-400 text-xs">Tokens Depois</p>
                  <p className="text-2xl font-bold text-green-400">{String(result.tokens_after)}</p>
                </div>
                <div className="bg-dark-800 rounded-lg p-4 border border-gray-800">
                  <p className="text-gray-400 text-xs">Economia</p>
                  <p className="text-2xl font-bold text-primary-400">{String(result.savings_percent)}%</p>
                </div>
                <div className="bg-dark-800 rounded-lg p-4 border border-gray-800">
                  <p className="text-gray-400 text-xs">Latência</p>
                  <p className="text-2xl font-bold text-white">{String(result.latency_ms)}ms</p>
                </div>
              </div>
              <pre className="bg-dark-800 border border-gray-700 rounded-lg p-4 text-green-300 font-mono text-xs overflow-auto max-h-96">
                {JSON.stringify(result, null, 2)}
              </pre>
            </div>
          ) : (
            <div className="bg-dark-800 border border-gray-800 rounded-lg p-12 text-center text-gray-500">
              Execute uma compressão para ver os resultados
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
