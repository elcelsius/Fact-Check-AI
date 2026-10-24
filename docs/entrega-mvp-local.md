# Entrega do MVP local

**Versão 0.23.0 · 24 de outubro de 2026**

O escopo escolhido pelo proponente é um **aplicativo local, com revisão humana e exportação**. O material de entrada pode ser um debate político, propaganda política, noticiário, entrevista ou outro conteúdo falado. O evento que motivou o projeto já passou; esta versão prepara o trabalho com gravações e futuras transmissões. Nenhum evento ou revisor foi presumido.

Esta entrega encerra a implementação desse primeiro escopo para ensaios internos. A aprovação editorial e o desempenho em uma transmissão representativa exigem avaliação humana. O [checklist amplo](checklist-desenvolvimento.md) continua registrando o piloto, a avaliação e evoluções além desta entrega; suas 130 tarefas não são requisitos todos atendidos por uma versão local.

## Recursos e critérios de entrega

| Etapa | Disponível | Critério técnico exercitado |
| --- | --- | --- |
| Entrada | Captura da saída Windows ou **Ensaiar WAV salvo** | Áudio PCM preservado; WAV de ensaio alimenta a mesma fila no ritmo original, sem abrir dispositivo ou reproduzir som. |
| Transcrição | Reconhecimento local contínuo ou Whisper, prévia e parágrafos | Prévia separada do texto estabilizado; fila, cancelamento e histórico preservam os arquivos concluídos. |
| Contexto | Tipo, título, data, URL, participantes e minutagem de referência | Sessões antigas abrem com tipo não informado; mudanças de contexto invalidam análises dependentes. |
| Falantes | Separação local em vozes anônimas após encerrar a captura | Associação exige ouvir, escolher participante cadastrado e justificar; mistura de vozes ou revisão antiga bloqueia aplicação em lote. |
| Triagem | Qwen local ou Gemini opcional, categorias e temas | Citações precisam pertencer à fala; correções preservam histórico; relato de terceiros exige conferir atribuição e contexto. |
| Pesquisa | Plano, navegador, coleção, antecedentes, Tavily opcional, coleta e importação | URLs candidatas e cópias importadas têm origem identificada; documentos e conclusões guardam versões. |
| Revisão | Correção da fala e da extração, evidências e decisão humana | Conferência textual, atribuição de voz, análise preliminar e veredito são estados distintos. |
| Saída | JSON, CSV, dossiê Markdown e relatório JSON/TXT | Escrita atômica, cancelamento e exportação de pendências identificadas; nenhum envio automático. |
| Continuidade | Reabrir, diagnosticar e recuperar sessão interrompida | Ensaio com queda de subprocesso preservou áudio, revisão e decisão já confirmada, sem retomar APIs. |
| Manutenção | Suíte Windows, validação de links/versões/SVGs e construção do pacote | Workflow versionado em [tests.yml](../.github/workflows/tests.yml); execução remota deve ser conferida no GitHub. |

## Como experimentar

1. Abra **iniciar.cmd**. Em **Dados da transmissão**, escolha o tipo e confira a data das declarações. Em notícia reexibida ou propaganda que usa imagens antigas, a data de upload pode não ser a data da fala.
2. Para vídeo tocando, escolha a saída de áudio e **Iniciar captura**. Para material existente, use **Ensaiar WAV salvo** com WAV PCM16. O ensaio termina automaticamente no fim do arquivo e cria outra sessão; o original permanece intacto.
3. Aguarde o encerramento. Ouça e corrija os parágrafos em **Revisar falas**. Para auxiliar a atribuição, abra **Falantes**, prepare os modelos uma vez e analise a gravação. Selecione trechos da mesma voz, ouça cada um e confirme sua associação a um participante.
4. Confira citação, resumo, categoria, tema e quem de fato afirma o conteúdo. Uma frase do apresentador como “segundo a candidata...” relata uma declaração de terceiro: o nome citado não identifica a voz atual.
5. Abra o dossiê, defina pergunta, período, território, indicador e comparação. Colete documentos pertinentes ou importe cópias, conferindo sua origem. Registre a decisão humana e a justificativa depois de ler as evidências.
6. Exporte a sessão e o dossiê. Reabra a sessão e confira uma fala, uma fonte e o estado da decisão nos arquivos. Pendências continuam explícitas.

As instruções de instalação estão no [README](../README.md#preparar-um-ambiente-novo). O [guia operacional](operacao-e-recuperacao.md) detalha cada controle e o ensaio de recuperação. A [metodologia editorial proposta](metodologia-editorial.md) orienta a conferência, sem declarar uma validação editorial já realizada.

## Falantes: alcance e privacidade

O motor sherpa-onnx agrupa intervalos como **Voz 1, Voz 2...** dentro de uma análise. Números podem mudar em outra execução. O modelo não identifica candidatos ou jornalistas pelo nome e não compara pessoas entre sessões. A quantidade informada pelo operador pode forçar grupos; zero solicita estimativa. Vozes simultâneas, locução, música e trechos curtos podem causar erros. A cobertura mostrada é duração detectada, não probabilidade de acerto.

O download explícito de aproximadamente 47 MB usa ativos fixados do projeto sherpa-onnx, com SHA-256 e extração restrita. Depois da preparação, o áudio e o processamento permanecem locais. O SQLite guarda intervalos anônimos e a justificativa da associação; os arquivos exportados levam a atribuição humana e sua proveniência, sem copiar toda a análise anônima. Corrigir o participante aumenta a revisão da fala, exige nova triagem e mantém vereditos anteriores como históricos. A atribuição não marca o texto como conferido.

Referências técnicas: [diarização sherpa-onnx](https://k2-fsa.github.io/sherpa/onnx/speaker-diarization/index.html), [modelos de segmentação](https://github.com/k2-fsa/sherpa-onnx/releases/tag/speaker-segmentation-models) e [modelos de voz](https://github.com/k2-fsa/sherpa-onnx/releases/tag/speaker-recongition-models). O modelo de segmentação inclui licença MIT preservada no diretório local de modelos.

## Validação desta entrega

- O ensaio da gravação portuguesa existente, com 20,011 s, gerou três segmentos estáveis e um parágrafo, sem APIs. A cópia WAV resultante foi idêntica ao original, que permaneceu intacto. Foram cerca de 44,2 s incluindo preparação e finalização; a primeira prévia chegou em cerca de 2,88 s após iniciar a entrada. A fila atingiu 50 pacotes, sem transbordar nesse trecho curto.
- A medição isolada com quatro threads consumiu 33,42 s de processamento para esses 20,011 s, razão 1,67. Portanto, este ensaio **não sustenta promessa de acompanhar uma transmissão longa sem acumular atraso**. Os números mais rápidos da versão 0.3 são históricos de outra execução; a latência precisa ser medida novamente nas condições reais de uso. Diminuir o pacote de 0,2 s não resolve capacidade de processamento insuficiente.
- O processo Windows real de falantes analisou um áudio público de 56,861 s em cerca de 22,8 s de inferência, produzindo dez intervalos e quatro grupos. Quatro vozes foram solicitadas no teste; o resultado não mede acurácia nem qualidade em português. Nenhum nome foi atribuído automaticamente.
- A inspeção visual cobriu captura e aba de falantes em 1120×860 e 1000×760, confirmação de associação em 820×700 e 740×640 e cadastro da transmissão em 850×660 e 800×640. Foram usados dados fictícios.
- O ensaio de queda preservou aproximadamente 2,6 s de PCM, revisões e decisão já salva; transação incompleta foi revertida. Os materiais privados, modelos e saídas de verificação permanecem ignorados pelo Git.

A suíte automatizada e o resultado remoto são registrados no [README](../README.md#diagnóstico-e-testes) e no histórico do GitHub. Os testes com APIs usam transporte simulado; nenhum token real ou gravação privada integra o repositório.

## Condições de uso e evolução

O aplicativo opera na conta Windows e nos arquivos deste computador. Nomes de responsáveis organizam os casos, sem autenticar usuários. Contas, permissões e sincronização entre operadores ficam para outra versão. Faça cópia da pasta de sessão somente depois de encerrar as atividades e guarde-a em local sob seu controle.

A pesquisa é iniciada pelo operador. Gemini e Tavily exigem chaves individuais, mantidas em memória; chamadas reais, cotas e pertinência ainda precisam ser conferidas com as chaves do usuário. A coleta automática continua limitada aos domínios institucionais permitidos. Um noticiário pode ser material de entrada sem que qualquer site se torne fonte aprovada. Não há OCR ou garantia de interpretação de tabelas complexas. A análise de falantes é posterior à captura, limitada a WAV de até três horas e a trinta minutos por tarefa; use trechos menores se necessário.

Antes de um evento, escolha uma gravação representativa e prepare uma referência humana: texto correto, falantes, afirmações e evidências. Meça fidelidade, cobertura, falsos positivos, tempo de revisão e atraso de transcrição com e sem triagem simultânea. Registre também as abstenções. Esse é o marco de validação editorial e operacional que permanece aberto; conclusões públicas continuam dependendo de especialistas humanos.
