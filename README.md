# Fact-Check AI

Checagem assistida por IA em debates políticos ao vivo.

Projeto de um assistente de pesquisa para equipes humanas de checagem. Durante um debate, o sistema deverá transcrever falas, identificar afirmações verificáveis, pesquisar evidências e preparar análises preliminares para revisão editorial.

**Status:** protótipo local de captura, transcrição contínua e organização em parágrafos, versão 0.4, de 22 de outubro de 2026. A identificação dos participantes, a pesquisa de evidências e o painel editorial fazem parte dos próximos incrementos.

## Usar o protótipo

No Windows, abra **iniciar.cmd** com dois cliques. Na janela:

1. Reproduza um vídeo com fala em português no navegador.
2. Selecione a saída usada para ouvir o vídeo, como alto-falantes ou monitor.
3. Mantenha **Transcrever durante a gravação** marcado, escolha **Contínua · prévia durante a fala** e clique em **Iniciar captura**.
4. Acompanhe o nível do áudio, a fala em andamento e os parágrafos com horários. A pausa entre parágrafos começa em **1,5 segundo** e pode ser ajustada antes da captura.
5. Clique em **Encerrar e salvar**. A janela aguarda os trechos pendentes e permite abrir a pasta da sessão.

Para interromper a sessão sem aguardar todas as transcrições pendentes, use **Cancelar sessão** e confirme. A captura termina, os resultados pendentes são cancelados e os arquivos já gravados são preservados com estado **cancelled**. Um trecho que já esteja em processamento termina antes de liberar a sessão. Se recusar a confirmação, a captura continua normalmente.

Ao fechar a janela durante a preparação, gravação ou transcrição, o aplicativo exige confirmação, com **Não** como escolha padrão. Confirmar interrompe a gravação, cancela as pendências e descarta o texto provisório. O áudio, os trechos e os parágrafos já gravados são preservados; a janela aguarda a finalização dos arquivos antes de fechar. Para concluir as transcrições pendentes, use **Encerrar e salvar** e aguarde o fim da sessão antes de fechar. Sem trabalho ativo, a janela fecha diretamente.

A proteção de fechamento também considera outras tarefas registradas em segundo plano e aguarda seu encerramento. Essa integração foi testada com uma checagem simulada; a pesquisa e a checagem de fatos ainda serão implementadas.

A captura acompanha a saída de áudio selecionada e inclui outros sons reproduzidos nela. O modo contínuo mantém o estado do reconhecimento e recebe pacotes sem sobreposição a cada **0,2 segundo**, usando Nemotron 3.5 ASR Streaming pelo sherpa-onnx, em CPU/int8 e português brasileiro. O arquivo WAV preserva o formato nativo; o motor converte o sinal para mono e reamostra internamente para 16 kHz. [Documentação do modelo contínuo](https://k2-fsa.github.io/sherpa/onnx/nemo/nemotron-streaming.html#sherpa-onnx-nemotron-3-5-asr-streaming-0-6b-560ms-int8-2026-06-11-multilingual)

O campo **Em andamento** contém uma hipótese que pode mudar ou terminar com uma palavra incompleta. Ela substitui a prévia anterior e não é gravada como transcrição definitiva. Os trechos estabilizados são salvos após a detecção de uma pausa, um limite de segmento de aproximadamente 15 segundos ou o encerramento normal. O motor usa 0,8 segundo de silêncio como um dos critérios de pausa. Esses trechos alimentam a organização em parágrafos. Estabilizado significa somente que o reconhecimento encerrou aquele segmento; a revisão humana permanece pendente.

**Pacotes de 0,2 segundo não significam palavras prontas em 0,2 segundo.** A primeira prévia depende da chegada da fala e do processamento. Os horários são estimativas do reconhecimento, não marcações conferidas palavra por palavra. Se o dispositivo suspender as amostras durante o silêncio, a estabilização pode aguardar novas amostras ou o encerramento.

O modo **Whisper · trechos a cada três segundos** continua disponível para comparação. Ele usa o modelo small do faster-whisper, envia o primeiro trecho após dois segundos e mantém até seis segundos de contexto. A escolha do modo acontece antes de iniciar a sessão.

### Organização em parágrafos

A versão 0.4 usa regras locais de português para sugerir a organização do texto, sem uma chamada adicional a serviços de IA. O parágrafo aparece assim que chega um trecho estabilizado e pode crescer com os trechos seguintes. A decisão de abrir outro parágrafo acontece quando chega a fala seguinte, considerando:

| Sinal | Critério inicial |
| --- | --- |
| Pausa curta | Manter o parágrafo, com sugestão de ponto entre frases aparentemente completas. |
| Pausa de pelo menos 1,5 s | Sugerir outro parágrafo quando a ideia anterior parece concluída e a próxima fala não começa como complemento. |
| Complemento ou frase incompleta | Unir falas como “criamos vinte mil empregos” + “no estado”, “de oito para” + “seis por cento” ou uma negação ainda sem complemento. |
| Transição explícita | Reconhecer expressões como “mudando de assunto” e “quanto à saúde”, após uma ideia aparentemente concluída. |
| Fala longa | Após 30 s ou 90 palavras, procurar uma separação adequada entre os trechos seguintes; os limites são suaves. |
| Identificação de falante disponível | Separar quando a identificação muda. A atribuição automática dos participantes ainda está pendente. |

A pausa pode ser configurada de **0,8 a 5 segundos**. Os horários são os estimados pelo reconhecimento. A conclusão de uma ideia é uma heurística que considera conectivos, verbos, auxiliares e finais incompletos; a compreensão semântica geral, as mudanças implícitas de tema e a extração de afirmações continuam pendentes de desenvolvimento e avaliação.

A pontuação e a capitalização são sugestões de apresentação. **Ver texto original** permite acompanhar as mesmas falas sem essas sugestões. Os registros originais permanecem em **transcript.jsonl** e **transcript.txt**. Cada revisão de parágrafo mantém os identificadores e textos dos trechos de origem, e continua marcada como não revisada por uma pessoa. O encerramento normal inclui o último trecho; cancelar preserva os parágrafos já persistidos e descarta os resultados pendentes.

### Volume e nível do sinal

O volume do player e o mixer podem alterar as amostras capturadas. A intensidade ouvida nos alto-falantes não é uma medida suficiente da qualidade do sinal digital. Observe as indicações **Sem sinal**, **Sinal baixo**, **Sinal presente** e **Perto do limite** no aplicativo; os limites são indicadores operacionais, sem garantia de precisão da transcrição. Ajuste a reprodução se o sinal estiver muito fraco ou distorcido e mantenha o volume de escuta confortável. [Controles de volume do Windows](https://learn.microsoft.com/en-us/windows/win32/coreaudio/session-volume-controls)

Cada sessão cria uma pasta exclusiva em **recordings**, contendo:

| Arquivo | Conteúdo |
| --- | --- |
| audio.wav | Áudio PCM16 no formato nativo da saída selecionada. |
| transcript.txt | Trechos originais do reconhecimento, com horários relativos à sessão. |
| transcript.jsonl | Trechos estabilizados, horários, estado do reconhecimento e revisão humana pendente. |
| paragraphs.txt | Versão atual para leitura em parágrafos, com pontuação sugerida e horários. |
| paragraphs.jsonl | Histórico das revisões de cada parágrafo, motivos das quebras e trechos de origem. |
| session.json | Dispositivo, motor, modelo, revisão do modelo, cadência, duração e problemas registrados. |
| events.jsonl | Tempos de processamento, falhas e intervalos preenchidos com silêncio. |

O modelo contínuo ocupa aproximadamente 682 MB e é baixado para **models** na primeira preparação, com revisão fixada no código. Após o download, a transcrição usa os arquivos locais. No modo contínuo, se a fila exceder dez segundos de áudio ou ocorrer uma falha do motor, a transcrição é interrompida e a prévia é limpa; a captura continua preservando o áudio, com aviso e registro de incompletude. Isso evita continuar um reconhecimento com amostras ausentes. No modo Whisper, as faixas não processadas são registradas para reprocessamento. A escolha de um falante ainda permanece indefinida nos registros.

Alguns players podem impedir a captura de áudio protegido. O projeto usa apenas a captura normal disponibilizada pelo Windows. [WASAPI loopback](https://learn.microsoft.com/en-us/windows/win32/coreaudio/loopback-recording)

## Preparar um ambiente novo

Ambiente inicial: Windows 11, Python 3.12, transcrição em CPU. Para obter o projeto, execute em PowerShell:

```powershell
git clone https://github.com/elcelsius/Fact-Check-AI.git
cd Fact-Check-AI
```

Na pasta do projeto, prepare o ambiente:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
.\.venv\Scripts\python.exe -m factcheck --prepare-model
.\iniciar.cmd
```

As versões verificadas estão em **requirements.lock**. O leitor PyAV está limitado a uma versão compatível com o faster-whisper utilizado. Implementações de referência: [PyAudioWPatch](https://github.com/s0d3s/PyAudioWPatch), [sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx) e [faster-whisper](https://github.com/SYSTRAN/faster-whisper).

## Diagnóstico e testes

```powershell
.\.venv\Scripts\python.exe -m factcheck --list-devices
.\.venv\Scripts\python.exe -m factcheck --record-seconds 20
.\.venv\Scripts\python.exe -m factcheck --record-seconds 5 --no-transcription
.\.venv\Scripts\python.exe -m factcheck --engine whisper --prepare-model
.\.venv\Scripts\python.exe -m factcheck --engine whisper --record-seconds 20
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Para escolher uma saída pela linha de comando, acrescente **--device** com o índice informado pela listagem. **--engine streaming** é o padrão; **--model tiny|base|small** se aplica ao modo Whisper. **--paragraph-pause 1.5** configura a pausa sugerida entre parágrafos. Os testes verificam preservação de amostras, formato WAV, medição de nível, horários, união das janelas, substituição das prévias, organização em parágrafos, encerramento, falhas e cancelamento. As gravações, modelos, caches e logs são ignorados pelo Git.

**paragraphs.jsonl** é um histórico de atualizações: para obter o estado atual, selecionar a maior **version** de cada **paragraph_id** dentro da sessão. O campo **closed** indica que o agrupamento foi encerrado, e **end_reason** distingue conclusão, cancelamento e interrupção; isso não equivale a validação editorial.

### Validação realizada neste computador

- Os 57 testes automatizados passaram, incluindo confirmação recusada e aceita ao cancelar ou fechar, espera pela finalização dos arquivos, checagem simulada sem gravação ativa, cancelamento durante processamento nos dois motores, preservação do áudio e dos parágrafos, revisão da prévia, continuidade de comparações e negações, fila cheia e falha do reconhecimento. A verificação de dependências também passou.
- A captura real do vídeo reproduzido pelo usuário salvou 20,011 segundos, estéreo, a 48 kHz, sem falhas sinalizadas pelo dispositivo. Os registros estão na sessão **20261022T215757Z_197ef367**.
- Na versão inicial, o modelo base processou as cinco janelas dessa sessão em até 0,854 segundo por janela. O modelo small processou o mesmo áudio salvo em 10,798 segundos no total, com até 2,402 segundos por janela. Essas medidas descrevem apenas esse trecho e a configuração CPU/int8 usada no experimento.
- Na versão 0.2 com Whisper, o primeiro texto teve entrega estimada em aproximadamente 4,1 segundos sobre o vídeo salvo, por simulação da fila. Na versão 0.3 foi feito um novo ensaio alimentando o motor contínuo no ritmo original, com pacotes de 0,2 segundo, sem reproduzir som nem capturar novo áudio:

| Ensaio contínuo em CPU | Fala sintética conhecida, 13,17 s | Vídeo salvo, 20,01 s |
| --- | --- | --- |
| Primeira prévia desde o início do arquivo | 0,87 s | 1,54 s |
| Processamento por pacote, percentil 95 | 0,215 s | 0,175 s |
| Processamento total / duração do áudio | 0,58 | 0,52 |
| Processamento adicional ao encerrar | 0,55 s | 0,48 s |

Essas medidas excluem a preparação inicial do modelo (1,2–1,4 s nesses ensaios), a captura do dispositivo e a atualização visual da janela, que consulta eventos a cada 100 ms. A primeira prévia também inclui eventual silêncio inicial. A métrica por pacote mede computação e não equivale ao atraso até reconhecer uma palavra. Os dados descrevem dois trechos neste computador, sem garantia para outros conteúdos ou máquinas. O vídeo ainda contém erros e grafias inconsistentes em nomes; o conjunto de avaliação humana continua pendente.

A sessão completa também foi exercitada com o vídeo salvo, simulando a chegada das amostras ao capturador: gerou prévias, persistiu três segmentos estabilizados, manteve todas as amostras originais e terminou sem problemas registrados. Na versão 0.4, o ensaio com a fala conhecida gerou três parágrafos, preservando todos os trechos originais e sem duplicações no arquivo de leitura. Esses ensaios usam um dispositivo simulado; a organização deve ser avaliada com mais falas reais. As janelas das versões 0.3 e 0.4 foram abertas e inspecionadas visualmente. Para repetir o ensaio no ritmo original com um WAV PCM16 já salvo:

```powershell
.\.venv\Scripts\python.exe -m scripts.benchmark_streaming recordings\PASTA_DA_SESSAO\audio.wav
```

O relatório detalhado fica em **.cache/verification/streaming-paced.json**, incluindo prévias, segmentos estabilizados e seus tempos de entrega. O áudio não é enviado a serviços de transcrição.

## Documentação

A [proposta inicial](docs/proposta-inicial.md) é a referência local para a evolução do projeto. Ela contém:

- Problema, proposta de valor, usuários e responsabilidades.
- Escopo do primeiro piloto em um debate político ao vivo.
- Fluxo operacional e funções dos agentes de IA.
- Metodologia, classificações e critérios para tratar incertezas.
- Estrutura do dossiê, exemplo e requisitos de aceitação.
- Arquitetura proposta, plano do piloto e métricas de avaliação.
- Riscos, decisões pendentes, backlog e referências.

O [checklist de desenvolvimento](docs/checklist-desenvolvimento.md) detalha as tarefas, dependências, responsáveis sugeridos e critérios de conclusão de cada fase. Os arquivos deste repositório são a referência para acompanhar o andamento técnico.

## Premissas centrais

A equipe humana validará cada dossiê e decidirá sobre qualquer divulgação. A análise preliminar deverá apresentar evidências consultáveis, contexto e lacunas.

O primeiro piloto acompanhará um debate político ao vivo em uso interno. Um ensaio com gravação permitirá testar a operação antes do evento.

O projeto avaliará a redução de trabalho humano junto com a qualidade das evidências, a cobertura das afirmações, o tempo até a revisão e o custo. Tecnologias, orçamento, equipe, evento e metas operacionais serão definidos na preparação do piloto.

## Próximo marco

Conferir o protótipo com áudio real e avaliar a transcrição em português. Depois, acrescentar cadastro da sessão e dos participantes, correção de transcrição e identificação das afirmações. A definição editorial do piloto e seu conjunto de referência humana continuam no checklist.
