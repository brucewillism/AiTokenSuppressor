import { getApiDisplayInfo } from '../services/api';

interface ApiConnectionHintProps {
  error?: string | null;
}

export default function ApiConnectionHint({ error }: ApiConnectionHintProps) {
  const { url, host, port } = getApiDisplayInfo();

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
      <p className="text-gray-600 mt-4 text-xs leading-relaxed px-4">
        Pode ser o contêiner da API ainda inicializando, serviço parado ou bloqueio de
        firewall na porta <span className="font-mono text-gray-500">{port}</span>.
        Confirme também que <code className="text-gray-500">VITE_API_URL</code> no build
        aponta para o backend correto.
      </p>
    </div>
  );
}
