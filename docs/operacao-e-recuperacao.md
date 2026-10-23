# Operação e recuperação de uma sessão

Procedimento do protótipo Windows, versão **0.13.0**, de 23/10/2026. As funções são locais; nenhuma pesquisa ou chamada à IA é retomada automaticamente ao abrir uma sessão.

## Antes de um ensaio com vídeo

1. Registre a versão exibida na janela e o vídeo usado. Prefira uma gravação conhecida antes de acompanhar um evento ao vivo.
2. Confira espaço em disco, saída de áudio, sinal no medidor e idioma da fala. Não use o áudio da revisão enquanto a captura estiver ativa.
3. Cadastre o evento e os participantes. Depois do início efetivo da captura, informe a minutagem correspondente no vídeo.
4. Confira o motor de IA. Local funciona sem enviar falas; Gemini exige a chave do usuário e acesso à rede. Use **Testar conexão** antes do ensaio se escolher Gemini.
5. Faça uma captura curta e use **Encerrar e salvar**. Confira áudio, texto e a pasta da sessão antes da captura principal.

Capturas independentes em duas máquinas podem servir como redundância, com identificação e minutagem próprias. A troca automática entre operadores, a sincronização entre máquinas e a remoção de duplicações ainda não existem.

## Encerrar normalmente

Use **Encerrar e salvar** para deixar a transcrição concluir os trechos recebidos. **Cancelar sessão**, mediante confirmação, preserva arquivos e resultados já salvos e descarta resultados pendentes. Fechar com captura, pesquisa, exportação ou recuperação em andamento pede confirmação e aguarda o cancelamento das atividades.

Os metadados distinguem captura, finalização e estado final. São gravados em arquivo temporário, sincronizados e substituídos por inteiro. O WAV atualiza o cabeçalho por pacote e descarrega seus buffers ao sistema pelo menos a cada segundo em que recebe amostras. Isso reduz o dano de um processo encerrado, sem garantir persistência diante de falha elétrica ou defeito do armazenamento.

## Retomar depois de uma queda

1. Confirme que a execução anterior terminou. Preserve uma cópia da **pasta inteira da sessão** antes de investigar arquivos danificados. Se ainda houver processo ativo, aguarde seu encerramento; não copie apenas o banco enquanto ele estiver sendo alterado. Arquivos auxiliares do SQLite também podem ser necessários.
2. Abra o aplicativo e use **Revisar falas → Abrir sessão gravada**. Selecione a pasta em `recordings`.
3. Use **Estado da sessão**. Confira o estado da captura, as falas salvas, os parágrafos sem encerramento, as tarefas interrompidas no histórico e o áudio presente. A contagem histórica inclui tentativas anteriores, mesmo quando uma tentativa posterior já foi concluída.
4. Se aparecer **Criar cópia recuperada do áudio**, use o botão. A cópia é preparada em segundo plano; **Cancelar recuperação** pede confirmação. Ao concluir, **Ouvir trecho** passa a usar a cópia, inclusive após reabrir a sessão. O original permanece preservado.
5. Ouça e confira o último trecho. **Encerrar parágrafos pendentes** exige confirmação e encerra somente a organização do texto que já existe. Não recupera palavras perdidas, não confere a transcrição e não inicia análise. O texto corrigido e os originais são preservados; uma nova revisão e um evento no histórico identificam a ação.
6. Revise conteúdo, participante e contexto. Use **Analisar seleção** para uma nova triagem ou retome uma coleta/análise no dossiê. A chave Gemini precisa ser informada novamente, salvo quando fornecida pelo ambiente. Pesquisas interrompidas ficam registradas e não são reenviadas ao serviço automaticamente.
7. Para voltar à transmissão, **inicie outra captura** e confira a nova minutagem. O áudio e o texto anteriores permanecem na sessão original. Preserve o identificador do evento ao continuar o mesmo debate e anote a lacuna entre as sessões.
8. Exporte os dados necessários e confira o arquivo. Registre o incidente, o horário aproximado, os trechos faltantes e as tarefas repetidas. Uma exportação é um retrato dos registros; a cópia completa da pasta é necessária para conservar áudio e histórico integral.

## O que a recuperação permite afirmar

| Situação | Comportamento |
| --- | --- |
| Captura/finalização com processo responsável encerrado | Mostra interrupção sem finalização. Os metadados originais não são reescritos ao abrir. |
| Captura/finalização com processo ainda ativo | Bloqueia a abertura como sessão gravada e o reparo. A detecção por PID é conservadora; um PID reutilizado pode impedir a recuperação até investigação. |
| Sessão antiga sem identificação do processo ou metadados ilegíveis | Mostra estado não confirmado. Um banco já inicializado pode ser consultado; o reparo e o encerramento de parágrafos ficam bloqueados. Metadados ilegíveis sem banco inicializado exigem investigação da cópia. |
| Última linha JSONL incompleta ou inválida, sem quebra final | Importa os registros completos e mostra aviso com o número da linha; preserva o arquivo e as revisões humanas. O aviso não prova a causa do dano. |
| Linha inválida no meio, linha inválida encerrada por quebra ou registro incompatível | Bloqueia a importação antes de aplicar os registros do arquivo. Preserve a pasta para investigação. |
| WAV PCM16 do capturador com cabeçalho ou última amostra incompletos | Permite criar cópia com todas as amostras completas presentes; informa bytes finais descartados. Não inventa áudio nem preenche lacunas. |
| Áudio ausente ou formato diferente do WAV padrão do capturador | Informa indisponibilidade; não tenta adivinhar o formato. |
| Triagem ou pesquisa de processo encerrado | Marca interrupção com data e histórico. Resultados e decisões já salvos permanecem; a nova tentativa depende do operador. |
| Exportação interrompida | Um temporário não é promovido a arquivo concluído. O destino só é substituído após a escrita completa; depois de uma queda, repita a exportação e confira o resultado. |

As cópias de áudio ficam em `recovered/`, com nome associado ao tamanho, data de modificação e cabeçalho do original. Não substituem `audio.wav`. A aplicação confere formato e extensão dos dados antes de reproduzi-las; essa identificação não equivale a autenticação criptográfica do conteúdo. Não edite os arquivos de áudio manualmente durante a recuperação.

O encerramento manual aparece como `recovery_closure` no JSON e nas colunas `encerramento_recuperado_em` e `motivo_encerramento_recuperado` do CSV de falas. Conferência da transcrição, análise preliminar e decisão humana permanecem estados distintos.

## Repetir o ensaio técnico de queda

```powershell
.\.venv\Scripts\python.exe -m scripts.rehearse_recovery
```

O script cria uma sessão descartável e um subprocesso próprio, captura PCM fictício pelo fluxo do capturador e encerra à força **somente esse subprocesso**. Os registros editoriais são inseridos como dados fictícios: o ensaio não carrega ASR, modelo de triagem, chave ou rede e não abre sessões reais. A pasta descartável é removida ao terminar; o relatório local fica em `.cache/verification/recovery-drill.json`.

Na execução da versão 0.12.0, foram conferidos:

- Detecção do processo ativo antes da queda e da interrupção depois dela.
- Reversão de uma transação SQLite não confirmada, preservando a correção humana e a decisão do dossiê.
- Aviso de cauda incompleta em UTF-8, sem reescrever o histórico original.
- Interrupção de uma triagem e uma pesquisa, sem nova tentativa automática.
- Reprodução dos **2,4 s de PCM disponíveis** com as amostras esperadas.
- Encerramento manual do parágrafo pendente, exportação após a retomada e reabertura repetível.

Testes adicionais verificam a cópia de um WAV com cabeçalho incompleto, a exclusão de um byte final sem amostra completa, cancelamento, mudança do arquivo durante a cópia, rejeição de corrupção intermediária e bloqueios da interface. A janela de estado foi inspecionada com dados fictícios.

Esse ensaio cobre encerramento de processo e persistência local. Continuam pendentes o ensaio editorial completo com vídeo representativo, qualidade da transcrição/checagem, falha elétrica, disco defeituoso ou cheio, recuperação entre máquinas e restauração de backup em outro computador. A chamada real ao Gemini e a coleta online ainda precisam ser validadas na execução normal do Windows.

## Ensaio editorial com gravação

1. Escolha um intervalo de três a cinco minutos com afirmações verificáveis, opiniões e frases que dependam de contexto. Registre vídeo, posição inicial, versão, operador e motor utilizado. Preserve o vídeo para rever a mesma fala.
2. Para preparar uma referência sem ver as sugestões, desmarque **Identificar afirmações automaticamente ao concluir cada parágrafo** antes da captura. Ouça e anote as afirmações elegíveis, com tempos e recortes. Separe essa referência das sugestões da IA; se usar revisão já assistida, registre essa condição.
3. Encerre a captura. Confira a transcrição, números, negações e participantes com o áudio. Registre correções necessárias, trechos ausentes e tempo gasto. As contagens automáticas do relatório não substituem essa conferência.
4. Execute a triagem nos parágrafos escolhidos. Compare as afirmações com a referência, incluindo as que a IA não identificou. Registre erros de extração, duplicações e tentativas rejeitadas. Uma resposta inválida permanece como falha; confira a fala antes de repetir a tentativa.
5. Para cada caso factual selecionado, colete uma fonte institucional ou importe uma cópia já baixada, conferindo a URL declarada. Verifique período, território, indicador, método e possíveis fontes divergentes. Uma cópia importada não comprova acesso à URL.
6. Se optar por Gemini, configure e teste sua chave antes da análise preliminar. Sem API, a equipe pode ler as fontes e revisar manualmente. Registre a decisão humana e a justificativa somente após a conferência; casos sem evidência suficiente podem permanecer inconclusivos. Não há publicação automática.
7. Exporte o JSON completo, os CSVs necessários e **Relatório do ensaio · TXT/JSON**, usando **Exportar sessão**. Abra os arquivos no destino e confira campos, texto, fontes e estados. O relatório usa as afirmações atuais; tentativas antigas ficam separadas, inclusive depois de uma nova tentativa bem-sucedida.
8. Preencha a ficha abaixo com a referência humana e as observações. Compare esforço, cobertura e falhas, mantendo o denominador das afirmações reais separado da quantidade detectada pela IA. Defina as correções e os limites aceitáveis antes de repetir ou avançar para um evento ao vivo.

### Como ler os tempos e denominadores

| Medida | Interpretação e limite |
| --- | --- |
| Decisões humanas / factuais identificadas | Usa apenas as declarações factuais detectadas pela IA, atuais e não descartadas. Não mede precisão nem recuperação das afirmações reais. Sem factuais atuais, a proporção fica indisponível. |
| Primeira prévia | Tempo desde o início efetivo da captura até a primeira hipótese não vazia registrada. Inclui eventual silêncio inicial; não é atraso por palavra e não mede a chegada visual na janela. |
| Primeira entrega estabilizada | Tempo desde o início da captura até a persistência do primeiro segmento estabilizado. Não garante fidelidade ao áudio. |
| Atraso dos segmentos | Tempo de entrega menos o fim estimado do segmento no áudio. Diferente do atraso de um pacote. Valores negativos ou inválidos são excluídos e contados. |
| Processamento e atraso de pacotes/trechos | Medições técnicas já registradas pelo capturador. O modo streaming usa pacotes; Whisper usa janelas com contexto. Não são métricas equivalentes ao reconhecimento de uma palavra. |
| Duração da triagem | Tempo registrado nas tentativas concluídas, incluindo preparação e esperas que ocorrerem na tentativa. As falhas aparecem nas contagens históricas; não são tratadas como duração zero. |
| Tempo até a decisão humana atual | Intervalo entre registro da afirmação e a decisão que continua válida. Inclui espera e pesquisa; não é tempo de trabalho humano. Usa relógio civil e exclui intervalos negativos ou horários sem fuso. |
| Primeira decisão atual desde a captura | Usa o horário explícito do início, quando disponível. Sessões antigas podem usar o evento inicial como aproximação, indicada no relatório. Não é histórico de decisões depois invalidadas. |
| Mediana e P95 | Cada distribuição informa observações válidas e excluídas. P95 usa interpolação linear apenas a partir de 20 observações; amostras menores não recebem um P95. |

O log registra `capture_started_at` no evento inicial e, nas novas capturas, os eventos `first_partial` e `transcript_delivered`, com tempos relativos monotônicos. Esses eventos não repetem o texto da fala. Gravações antigas não são reprocessadas nem recebem horários estimados de prévia ou estabilização. Um log parcial gera aviso e informa linhas inválidas; o relatório não altera os arquivos originais.

O relatório JSON usa `format: factcheck-session-report`, `schema_version: 1`. `session_snapshot_sha256` identifica os registros agregados, enquanto `content_sha256` identifica as métricas e limitações exportadas; `generated_at` fica fora desse hash. O banco é lido em uma transação e os arquivos de captura separadamente, após encerrar a captura. A revisão e a pesquisa podem continuar mudando o banco depois da cópia. Guarde a versão e os hashes ao comparar relatórios.

### Ensaio técnico com gravação existente na versão 0.13

Foi usada uma **cópia** de uma gravação já salva, com **336,341 s de PCM e 22 parágrafos**, preservando os hashes dos arquivos originais. O relatório inicial mostrou todos os parágrafos sem conferência, participante e triagem. As medições existentes de processamento por pacote tinham 1.682 observações, mediana de 0,068 s e P95 de 0,143 s; esses números não medem atraso por palavra. A primeira prévia e a entrega estabilizada não estavam registradas nessa captura antiga e ficaram indisponíveis.

Em seguida, a triagem local com Qwen foi executada nos **três primeiros parágrafos** da cópia: duas tentativas concluíram e uma foi rejeitada por citação inválida. Foram registrados oito itens: três factuais, quatro opiniões e um indefinido. As três factuais ficaram aguardando fontes, sem decisão humana; a tentativa rejeitada permaneceu como falha. Os relatórios posteriores conservaram essas pendências, sem chamada a API e sem alteração dos originais.

Trata-se de uma amostra pequena escolhida pela ordem da gravação, sem referência humana. Não estima precisão, taxa de falha geral ou redução de esforço. A tentativa inválida exige conferência e possível nova análise; a pesquisa de fontes, a revisão factual e o ensaio editorial completo continuam pendentes. Os relatórios e a cópia usados no teste ficam em diretórios locais ignorados pelo Git.

## Registro do ensaio operacional

Use esta ficha no próximo teste com vídeo, preenchendo apenas o que foi observado:

| Campo | Registro |
| --- | --- |
| Data, operador e versão | A preencher |
| Vídeo, evento e identificadores das sessões | A preencher |
| Saída de áudio, motor e referência de vídeo | A preencher |
| Primeira prévia e estabilização, com número de observações | A preencher |
| Falas elegíveis, afirmações identificadas e revisões humanas | A preencher |
| Primeiro dossiê e tempo até a decisão humana | A preencher |
| Falhas, lacunas, tentativas repetidas e resultados perdidos | A preencher |
| Arquivos exportados e conferência no destino | A preencher |
| Correções necessárias antes do próximo ensaio | A preencher |

O encerramento do ensaio técnico não libera o piloto ao vivo. A qualidade editorial e as condições operacionais permanecem nos critérios do [checklist](checklist-desenvolvimento.md).
