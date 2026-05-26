import { useState } from 'react';
import { api } from '../services/api';

const STRATEGIES = ['aggressive', 'balanced', 'ultra', 'semantic', 'code-focused', 'chat-focused'];

export default function Playground() {
  const [input, setInput] = useState('You are a helpful assistant.\n\nUser: Explain how to build a REST API with FastAPI including authentication, database models, and error handling. Provide detailed examples with code.');
  const [strategy, setStrategy] = useState('balanced');
  const [result, setResult] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleCompress = async () => {
    setLoading(true);
    setError(null);
    try {
      const messages = [
        { role: 'system', content: 'You are a helpful assistant.' },
        { role: 'user', content: input },
      ];
      const data = await api.compress(messages, strategy);
      setResult(data as Record<string, unknown>);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erro ao comprimir');
    } finally {
      setLoading(false);
    }
  };

  const handleOptimize = async () => {
    setLoading(true);
    setError(null);
    try {
      const messages = [
        { role: 'system', content: 'You are a helpful assistant.' },
        { role: 'user', content: input },
      ];
      const data = await api.optimize(messages, strategy);
      setResult(data as Record<string, unknown>);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erro ao otimizar');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-8">
      <div>
        <h2 className="text-2xl font-bold text-white">Playground</h2>
        <p className="text-gray-400 mt-1">Teste compressão e otimização de prompts em tempo real</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-2">Estratégia</label>
            <select
              value={strategy}
              onChange={(e) => setStrategy(e.target.value)}
              className="w-full bg-dark-800 border border-gray-700 rounded-lg px-4 py-2 text-white focus:ring-2 focus:ring-primary-500 focus:border-transparent"
            >
              {STRATEGIES.map((s) => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-300 mb-2">Prompt</label>
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              rows={12}
              className="w-full bg-dark-800 border border-gray-700 rounded-lg px-4 py-3 text-white font-mono text-sm focus:ring-2 focus:ring-primary-500 focus:border-transparent resize-none"
            />
          </div>

          <div className="flex gap-3">
            <button
              onClick={handleCompress}
              disabled={loading}
              className="flex-1 bg-primary-600 hover:bg-primary-700 disabled:opacity-50 text-white font-medium py-2.5 px-4 rounded-lg transition-colors"
            >
              {loading ? 'Processando...' : 'Comprimir'}
            </button>
            <button
              onClick={handleOptimize}
              disabled={loading}
              className="flex-1 bg-purple-600 hover:bg-purple-700 disabled:opacity-50 text-white font-medium py-2.5 px-4 rounded-lg transition-colors"
            >
              {loading ? 'Processando...' : 'Otimizar Completo'}
            </button>
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
