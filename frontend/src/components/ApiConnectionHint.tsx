import { getApiDisplayInfo } from '../services/api';

interface ApiConnectionHintProps {
  error?: string | null;
}

export default function ApiConnectionHint({ error }: ApiConnectionHintProps) {
  const { url, host, port, directHealthUrl } = getApiDisplayInfo();

  return (
    <div className="text-center py-20 max-w-lg mx-auto">
      {error && (
        <p className="text-red-400 text-lg font-medium">{error}</p>
      )}
      <p className="text-gray-400 mt-3 text-sm leading-relaxed">
        Verifique se a API está rodando e acessível em:{' '}
        <span className="text-primary-400 font-mono break-all">{url}</span>
      </p>
      <p className="text-gray-500 mt-2 text-xs">
        Host: <span className="font-mono">{host}</span>
        {' · '}
        Porta: <span className="font-mono">{port}</span>
      </p>
      {directHealthUrl && (
        <p className="text-gray-500 mt-2 text-xs">
          Teste direto da API (sem proxy):{' '}
          <a
            href={directHealthUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="text-primary-400 font-mono break-all hover:underline"
          >
            {directHealthUrl}
          </a>
        </p>
      )}
      <p className="text-gray-600 mt-4 text-xs leading-relaxed px-4">
        Pode ser o contêiner da API ainda inicializando, serviço parado ou bloqueio de
        firewall na porta <span className="font-mono text-gray-500">{port}</span>.
        Confirme que <code className="text-gray-500">DATABASE_URL</code> e{' '}
        <code className="text-gray-500">API_KEY</code> no arquivo <code className="text-gray-500">.env</code>{' '}
        estão corretos (o compose não deve sobrescrever com placeholders).
      </p>
      <p className="text-gray-600 mt-2 text-xs leading-relaxed px-4">
        Testes rápidos:{' '}
        <code className="text-gray-500">curl http://{host}:8100/health</code>
        {' · '}
        <code className="text-gray-500">curl http://{host}:8100/api/health</code>
      </p>
      <p className="text-gray-600 mt-2 text-xs leading-relaxed px-4">
        Redis no compose: <code className="text-gray-500">REDIS_URL=redis://redis:6379/0</code>.
        Rebuild UI após mudar API_KEY:{' '}
        <code className="text-gray-500">docker compose build --no-cache frontend</code>
      </p>
      <p className="text-gray-600 mt-2 text-xs leading-relaxed px-4">
        Na VPS: <code className="text-gray-500">docker compose ps</code> e{' '}
        <code className="text-gray-500">docker compose logs api --tail 50</code>
      </p>
    </div>
  );
}
