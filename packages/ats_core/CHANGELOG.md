# Changelog

## 0.1.1

- A última mensagem com papel `user` (turno final) é preservada literalmente em todas as estratégias, na deduplicação de mensagens, na deduplicação de linhas, no corte por `max_tokens` e no quality guard. Quando essa mensagem fecha o prompt, ela continua sendo a última.
- O corte por orçamento não apaga nem trunca esse turno, inclusive quando o texto passa de 500 caracteres.
- A deduplicação idêntica ou quase idêntica mantém a ocorrência mais nova e descarta a cópia anterior.
- A E.D.I.T.H. precisa repinar `ats_core` no SHA do merge desta versão. A tag não substitui o pin.

## 0.1.0

- Extração do núcleo puro de compressão para o pacote instalável `packages/ats_core`.
