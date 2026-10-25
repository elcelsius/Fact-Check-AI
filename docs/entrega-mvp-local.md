# Entrega do MVP local

**Fechamento técnico 0.25.0 · 25 de outubro de 2026**

Este documento preserva os ensaios da primeira entrega 0.23 e registra o fechamento 0.25. A **0.24.0** acrescentou Whisper NVIDIA e comparação automática; os [ensaios de desempenho](desempenho-transcricao.md) registram seus resultados e limites. As medições históricas abaixo mantêm a versão de origem.

O escopo escolhido pelo proponente é um **aplicativo local, com revisão humana e exportação**. O material de entrada pode ser um debate político, propaganda política, noticiário, entrevista ou outro conteúdo falado. O evento que motivou o projeto já passou; esta versão prepara o trabalho com gravações e futuras transmissões. Nenhum evento ou revisor foi presumido.

Esta entrega encerra a implementação desse primeiro escopo para ensaios internos. A aprovação editorial e o desempenho em uma transmissão representativa exigem avaliação humana. O [checklist amplo](checklist-desenvolvimento.md) continua registrando o piloto, a avaliação e evoluções além desta entrega; suas 130 tarefas não são requisitos todos atendidos por uma versão local.

## Recursos e critérios de entrega

A 0.25 completa os controles técnicos locais abaixo. A comprovação automatizada usa dados fictícios e transporte simulado para APIs; ela não substitui um ensaio editorial real.

| Complemento da 0.25 | Critério exercitado |
| --- | --- |
| Inclusão e divisão manuais | Citação literal, motivo e versão de origem obrigatórios; divisão atômica preserva o caso anterior e não copia vereditos. |
| Evidências e cálculos do operador | Citações ligadas a bloco e impressão digital do documento; fórmulas decimais sem execução de código, ligadas a citações atuais; mudanças invalidam conclusões. |
| Pesquisa em fila | Seleção explícita, plano conferido, prioridade entre casos, limites de casos/tarefas/fontes/tempo, cancelamento e interrupção após falha de API. |
| Pausa de captura | Áudio ignorado substituído por silêncio, mantendo o relógio; lacunas persistidas e propagadas aos parágrafos e exportações. Falas afetadas exigem conferência antes da triagem. |
| Uso de API | Reserva transacional de tentativas antes do envio; zero bloqueia novas chamadas de triagem/pesquisa; uso e estimativa financeira distinguem ausência de informação de gratuidade declarada. |
| Avaliação | Referência humana versionada, partições desenvolvimento/avaliação, WER e correspondência literal no subconjunto anotado; edição concorrente impede publicar métricas atuais. |
| Backup/restauração | Cópia SQLite consistente e arquivos permitidos com hashes; restauração em nova pasta, validação de caminhos/conteúdo e interrupção de tarefas antigas, sem reenvios. |

Em dados fictícios, o percurso inclusão → fonte → citação → cálculo → decisão humana de teste → exportação → restauração preservou decisão e proveniência. Captura, revisão, fila, dossiê e operação foram conferidos em 1120×860 e 1000×760, além dos novos editores. Os detalhes de uso estão no [guia operacional](operacao-e-recuperacao.md#controles-da-versão-025).

A tabela seguinte descreve a base entregue na 0.23 e mantida na 0.25; os números de testes e links de validação em suas linhas são históricos.

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
| Manutenção | Suíte Windows, validação de links/versões/SVGs e construção do pacote | [Workflow](../.github/workflows/tests.yml) aprovado em [execução Windows limpa](https://github.com/elcelsius/Fact-Check-AI/actions/runs/40135380140), com 510 testes, documentos, SVGs e recursos do pacote. |

## Como experimentar

As escolhas técnicas do escopo local estão consolidadas:

| Componente | Escolha e motivo | Alternativa e limite |
| --- | --- | --- |
| Painel | Python/Tkinter, aplicação Windows na conta do operador | Serviço web com contas fica fora do escopo; nomes locais não autenticam pessoas. |
| Áudio | WASAPI loopback, PCM16 e fila de captura independente | WAV no ritmo real permite ensaiar a mesma mídia; o aplicativo não controla o player. |
| Reconhecimento | sherpa-onnx contínuo local, CPU por padrão | faster-whisper small em CPU ou NVIDIA é escolha explícita; preparação e atrasos são medidos separadamente. |
| Triagem | Qwen local por processo, com validação do JSON e da citação | Gemini é opcional; envio exige configuração pelo usuário e passa pelo limite de tentativas. |
| Pesquisa | Coleta institucional, importação e fila sequencial solicitada pelo operador | Tavily descobre candidatas; Gemini analisa trechos coletados. Não há pesquisa autônoma irrestrita. |
| Persistência | SQLite por sessão, JSONL/TXT e WAV; biblioteca local separada | Transações e revisões rejeitam edições antigas; não há sincronização entre computadores. |
| Coordenação | Controladores de captura, triagem e pesquisa com cancelamento e comunicação por eventos | Modelos retornam dados validados, sem ferramenta para aprovar ou publicar. Decisão humana é uma operação separada. |
| Contratos e medição | Identidades, revisões, hashes, motor/prompt, tempos de etapa e uso de API quando informado | Adaptadores de transcrição, IA e busca ficam em módulos separados; trocas exigem testes do contrato, sem promessa de equivalência de qualidade. |

O diagrama [interno](diagramas/fluxo-interno.svg) mostra os limites dos componentes. Instalação e dependências estão no README; atualização/retorno e retenção estão no guia operacional. A autorização por papel do serviço multiusuário continua fora desta versão.

### Percurso sugerido

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

## Validação do fechamento 0.25

A suíte final passou localmente com **586 testes em 218.242 s**, incluindo os novos fluxos e falhas de armazenamento, além de sintaxe, links, contagem do checklist e SVGs. Os dois diagramas foram renderizados em navegador com verificação dos limites de todos os textos. A interface foi conferida em quinze vistas/tamanhos, com dados fictícios; o corte dos botões de revisão na janela mínima foi corrigido.

O ensaio de queda de processo foi repetido na 0.25: os 2,5 s de PCM disponíveis, revisão e decisão de teste permaneceram, a transação incompleta foi revertida e nenhuma tarefa foi reenviada. Backup/restauração preservou também uma cópia recuperada do áudio e seus metadados. O wheel foi construído e inspecionado: **59 arquivos públicos**, incluindo os novos módulos e o auxiliar PowerShell. Materiais privados continuam fora do pacote e do Git.

Os testes de APIs usam transporte simulado. As métricas de referência usam textos/anotadores fictícios e não estimam qualidade editorial real. O código mantém os resultados de desempenho da 0.24 como ensaios daquela versão; não foi presumido ganho de latência ou precisão por este fechamento.

A [execução Windows da 0.25 no GitHub](https://github.com/elcelsius/Fact-Check-AI/actions/runs/40156884167), em Windows 2022/Python 3.12 sobre o código `1efbdd3`, aprovou **587 testes em 624,023 s**, sintaxe, documentação, SVGs reproduzíveis e pacote. A última proteção do botão de pausa também passou em 32 testes locais de interface/captura. Os dados são fictícios e as APIs têm transporte simulado; nenhum veredito político real foi produzido.

## Validação histórica da primeira entrega 0.23

- O ensaio da gravação portuguesa existente, com 20,011 s, gerou três segmentos estáveis e um parágrafo, sem APIs. A cópia WAV resultante foi idêntica ao original, que permaneceu intacto. Foram cerca de 44,2 s incluindo preparação e finalização; a primeira prévia chegou em cerca de 2,88 s após iniciar a entrada. A fila atingiu 50 pacotes, sem transbordar nesse trecho curto.
- A medição isolada com quatro threads consumiu 33,42 s de processamento para esses 20,011 s, razão 1,67. Portanto, este ensaio **não sustenta promessa de acompanhar uma transmissão longa sem acumular atraso**. Os números mais rápidos da versão 0.3 são históricos de outra execução; a latência precisa ser medida novamente nas condições reais de uso. Diminuir o pacote de 0,2 s não resolve capacidade de processamento insuficiente.
- O processo Windows real de falantes analisou um áudio público de 56,861 s em cerca de 22,8 s de inferência, produzindo dez intervalos e quatro grupos. Quatro vozes foram solicitadas no teste; o resultado não mede acurácia nem qualidade em português. Nenhum nome foi atribuído automaticamente.
- A inspeção visual cobriu captura e aba de falantes em 1120×860 e 1000×760, confirmação de associação em 820×700 e 740×640 e cadastro da transmissão em 850×660 e 800×640. Foram usados dados fictícios.
- O ensaio de queda preservou aproximadamente 2,6 s de PCM, revisões e decisão já salva; transação incompleta foi revertida. Os materiais privados, modelos e saídas de verificação permanecem ignorados pelo Git.

A suíte passou localmente com **510 testes em 167,011 s** e no [GitHub Actions](https://github.com/elcelsius/Fact-Check-AI/actions/runs/40135380140) com **510 testes em 318,217 s**, em Windows 2022/Python 3.12 sobre o código `105aded`. A execução remota também aprovou sintaxe, documentação, SVGs reproduzíveis e construção do pacote com o auxiliar PowerShell. Os testes com APIs usam transporte simulado; nenhum token real ou gravação privada integra o repositório.

## Condições de uso e evolução

O aplicativo opera na conta Windows e nos arquivos deste computador. Nomes de responsáveis organizam os casos, sem autenticar usuários. Contas, permissões e sincronização entre operadores ficam para outra versão. Faça cópia da pasta de sessão somente depois de encerrar as atividades e guarde-a em local sob seu controle.

A pesquisa é iniciada pelo operador. Gemini e Tavily exigem chaves individuais, mantidas em memória; chamadas reais, cotas e pertinência ainda precisam ser conferidas com as chaves do usuário. A coleta automática continua limitada aos domínios institucionais permitidos. Um noticiário pode ser material de entrada sem que qualquer site se torne fonte aprovada. Não há OCR ou garantia de interpretação de tabelas complexas. A análise de falantes é posterior à captura, limitada a WAV de até três horas e a trinta minutos por tarefa; use trechos menores se necessário.

Antes de um evento, escolha uma gravação representativa e prepare uma referência humana: texto correto, falantes, afirmações e evidências. Meça fidelidade, cobertura, falsos positivos, tempo de revisão e atraso de transcrição com e sem triagem simultânea. Registre também as abstenções. Esse é o marco de validação editorial e operacional que permanece aberto; conclusões públicas continuam dependendo de especialistas humanos.
