# Fact-Check AI

Checagem assistida por IA em debates políticos ao vivo.

Projeto de um assistente de pesquisa para equipes humanas de checagem. Durante um debate, o sistema deverá transcrever falas, identificar afirmações verificáveis, pesquisar evidências e preparar análises preliminares para revisão editorial.

**Status:** protótipo com captura e transcrição locais, revisão das falas e triagem de afirmações local ou pela API Gemini, versão 0.6, de 22 de outubro de 2026. A identificação dos participantes é manual; a pesquisa de evidências e a revisão editorial dos dossiês fazem parte dos próximos incrementos.

## Usar o protótipo

No Windows, abra **iniciar.cmd** com dois cliques. Na janela:

1. Em **Dados do debate**, cadastre título, data, origem do vídeo e os participantes. O cadastro é opcional para um teste rápido.
2. Selecione a saída usada para ouvir o vídeo, como alto-falantes ou monitor.
3. Mantenha **Transcrever durante a gravação** marcado, escolha **Contínua · prévia durante a fala** e clique em **Iniciar captura**.
4. Acompanhe o nível do áudio, a fala em andamento e os parágrafos com horários. A pausa entre parágrafos começa em **1,5 segundo** e pode ser ajustada antes da captura.
5. Clique em **Encerrar e salvar**. A janela aguarda os trechos pendentes e permite abrir a pasta da sessão.

Na aba **Revisar falas**, selecione um trecho e use **Revisar fala selecionada** para corrigir o texto e atribuir o participante. **Ouvir trecho** reproduz o áudio do parágrafo depois de encerrar a captura, evitando gravar novamente o som da própria revisão. **Abrir sessão gravada** permite trabalhar com gravações anteriores, inclusive da versão 0.4.

Por padrão, parágrafos concluídos entram na triagem local automaticamente. **Configurar IA**, no topo da janela, permite escolher Gemini para as próximas análises. Você também pode usar **Analisar seleção** ou **Analisar todos os trechos concluídos**. Acompanhe a aba **Afirmações para checagem**: cada item mostra citação literal, resumo, participante informado, horário aproximado do parágrafo, contexto, campos extraídos e motor utilizado. **Revisar origem** abre a fala correspondente; **Descartar com justificativa** preserva o histórico.

Para interromper a sessão sem aguardar todas as transcrições pendentes, use **Cancelar sessão** e confirme. A captura termina, os resultados pendentes são cancelados e os arquivos já gravados são preservados com estado **cancelled**. Um trecho que já esteja em processamento termina antes de liberar a sessão. Se recusar a confirmação, a captura continua normalmente.

Ao fechar a janela durante a preparação, gravação ou transcrição, o aplicativo exige confirmação, com **Não** como escolha padrão. Confirmar interrompe a gravação, cancela as pendências e descarta o texto provisório. O áudio, os trechos e os parágrafos já gravados são preservados; a janela aguarda a finalização dos arquivos antes de fechar. Para concluir as transcrições pendentes, use **Encerrar e salvar** e aguarde o fim da sessão antes de fechar. Sem trabalho ativo, a janela fecha diretamente.

A proteção de fechamento também considera a triagem e editores abertos. Confirmar o fechamento cancela as análises pendentes e aguarda sua finalização; as já persistidas são mantidas. **Cancelar triagem** permite interromper somente a identificação de afirmações, com confirmação. A pesquisa e a checagem de fatos ainda serão implementadas.

A captura acompanha a saída de áudio selecionada e inclui outros sons reproduzidos nela. O modo contínuo mantém o estado do reconhecimento e recebe pacotes sem sobreposição a cada **0,2 segundo**, usando Nemotron 3.5 ASR Streaming pelo sherpa-onnx, em CPU/int8 e português brasileiro. O arquivo WAV preserva o formato nativo; o motor converte o sinal para mono e reamostra internamente para 16 kHz. [Documentação do modelo contínuo](https://k2-fsa.github.io/sherpa/onnx/nemo/nemotron-streaming.html#sherpa-onnx-nemotron-3-5-asr-streaming-0-6b-560ms-int8-2026-06-11-multilingual)

O campo **Em andamento** contém uma hipótese que pode mudar ou terminar com uma palavra incompleta. Ela substitui a prévia anterior e não é gravada como transcrição definitiva. Os trechos estabilizados são salvos após a detecção de uma pausa, um limite de segmento de aproximadamente 15 segundos ou o encerramento normal. O motor usa 0,8 segundo de silêncio como um dos critérios de pausa. Esses trechos alimentam a organização em parágrafos. Estabilizado significa somente que o reconhecimento encerrou aquele segmento; a revisão humana permanece pendente.

**Pacotes de 0,2 segundo não significam palavras prontas em 0,2 segundo.** A primeira prévia depende da chegada da fala e do processamento. Os horários são estimativas do reconhecimento, não marcações conferidas palavra por palavra. Se o dispositivo suspender as amostras durante o silêncio, a estabilização pode aguardar novas amostras ou o encerramento.

O modo **Whisper · trechos a cada três segundos** continua disponível para comparação. Ele usa o modelo small do faster-whisper, envia o primeiro trecho após dois segundos e mantém até seis segundos de contexto. A escolha do modo acontece antes de iniciar a sessão.

### Organização em parágrafos

O organizador usa regras locais de português para sugerir a organização do texto. O parágrafo aparece assim que chega um trecho estabilizado e pode crescer com os trechos seguintes. A decisão de abrir outro parágrafo acontece quando chega a fala seguinte, considerando:

| Sinal | Critério inicial |
| --- | --- |
| Pausa curta | Manter o parágrafo, com sugestão de ponto entre frases aparentemente completas. |
| Pausa de pelo menos 1,5 s | Sugerir outro parágrafo quando a ideia anterior parece concluída e a próxima fala não começa como complemento. |
| Complemento ou frase incompleta | Unir falas como “criamos vinte mil empregos” + “no estado”, “de oito para” + “seis por cento” ou uma negação ainda sem complemento. |
| Transição explícita | Reconhecer expressões como “mudando de assunto” e “quanto à saúde”, após uma ideia aparentemente concluída. |
| Fala longa | Após 30 s ou 90 palavras, procurar uma separação adequada entre os trechos seguintes; os limites são suaves. |
| Identificação de falante disponível | Separar quando a identificação muda. A atribuição automática dos participantes ainda está pendente. |

A pausa pode ser configurada de **0,8 a 5 segundos**. Os horários são os estimados pelo reconhecimento. A conclusão de uma ideia é uma heurística que considera conectivos, verbos, auxiliares e finais incompletos; mudanças implícitas de tema e a qualidade da segmentação continuam sujeitas a avaliação. A triagem das afirmações usa um modelo separado, descrito abaixo.

A pontuação e a capitalização são sugestões de apresentação. **Ver texto original** permite acompanhar as mesmas falas sem essas sugestões. Os registros originais permanecem em **transcript.jsonl** e **transcript.txt**. Cada revisão de parágrafo mantém os identificadores e textos dos trechos de origem, e continua marcada como não revisada por uma pessoa. O encerramento normal inclui o último trecho; cancelar preserva os parágrafos já persistidos e descarta os resultados pendentes.

### Triagem de afirmações e revisão

A identificação usa [Qwen3-4B-GGUF](https://huggingface.co/Qwen/Qwen3-4B-GGUF), quantização Q4_K_M, pelo [llama-cpp-python](https://github.com/abetlen/llama-cpp-python). O modelo ocupa aproximadamente **2,5 GB**, tem revisão fixada no código e executa em um processo local separado. Após preparar os modelos, a transcrição e a triagem funcionam sem enviar áudio ou falas a APIs de IA.

| Categoria da triagem | Encaminhamento |
| --- | --- |
| Declaração factual | **Aguardando pesquisa**, se não houver referência de contexto marcada. Isso não significa que seja verdadeira. |
| Fala com contexto relativo ou ambíguo | **Precisa de contexto**; expressões como “aqui”, “no estado” e “ano passado” permanecem literais. |
| Opinião ou promessa | Exibida como **Opinião / promessa**, fora da fila de pesquisa factual. Premissas factuais explícitas podem gerar itens separados. |
| Análise ligada a uma versão alterada | **Análise desatualizada**; requer nova triagem. |

As citações precisam corresponder a intervalos literais da versão analisada. Diferenças apenas de caixa, espaços ou pontuação terminal sugerida são restauradas ao texto da fonte e registradas. Não são aceitos prefixos de palavras ou números como citações completas. Campos de local, período, indicador ou comparação sem correspondência literal na citação são removidos e sinalizados. Resumos com número não fundamentado no texto ou que omitem uma negação explícita são substituídos pela citação. Essas validações limitam erros específicos e não garantem fidelidade semântica; a avaliação humana continua necessária.

Correções no texto, na atribuição do participante ou no cadastro do debate geram revisões e invalidam resultados dependentes. Resultados de uma análise que termina depois de uma correção são descartados como desatualizados. Se a transcrição original crescer após uma edição humana, a correção é preservada e o trecho é marcado para reconciliação, sem sobrescrever o trabalho do revisor. A conferência de uma transcrição é independente da validação factual.

A fila comporta até 30 análises pendentes, processadas uma de cada vez. A captura mantém suas próprias filas. Erros, cancelamento, respostas fora do formato, trechos além do limite do modelo e análises interrompidas aparecem para permitir nova tentativa; as falas continuam salvas. A velocidade depende do processador, da GPU, do tamanho da fala e da resposta. O primeiro uso da GPU pode levar mais tempo para preparar kernels e caches.

O banco **review.sqlite3** guarda o cadastro atual, originais, revisões humanas, análises e afirmações com histórico. Os arquivos de transcrição e parágrafos preservam o reconhecimento original; o texto corrigido aparece na aba de revisão e no banco. A identificação automática de quem fala, a pesquisa de fontes e as conclusões factuais continuam pendentes.

### Usar a API Gemini como alternativa

O modo inicial continua sendo **Local** em cada abertura do aplicativo. Para usar a API:

1. Crie uma chave no [Google AI Studio](https://aistudio.google.com/api-keys). Para usar somente a camada gratuita, escolha um projeto sem faturamento ativado e confira suas cotas.
2. Antes de iniciar uma captura, clique em **Configurar IA**, selecione **Gemini API** e preencha a chave no campo protegido. Também é possível definir **GEMINI_API_KEY** ou **GOOGLE_API_KEY** no ambiente antes de abrir o aplicativo.
3. Confira o aviso sobre envio de texto e clique em **Aplicar configuração**. A chave digitada fica apenas na memória desta execução, sem ser gravada pelo aplicativo em configurações, sessões, logs ou Git. Ela precisa ser informada novamente após fechar, salvo quando fornecida pelo ambiente.
4. Analise uma fala ou inicie uma captura com identificação automática. Para comparar uma fala já analisada pelo motor local, use **Analisar seleção**, que solicita nova análise da revisão atual.

O modelo configurado é **gemini-3.1-flash-lite**, cuja entrada e saída de texto têm camada gratuita na [tabela oficial consultada em 22/10/2026](https://ai.google.dev/gemini-api/docs/pricing#gemini-3.1-flash-lite). A disponibilidade e as cotas dependem do projeto. O aplicativo não consulta o estado de faturamento e não pode garantir custo zero em um projeto com cobrança habilitada. Não ativa faturamento, não troca de modelo e não muda de provedor automaticamente.

A fila começa com espaçamento de **5 chamadas por minuto**, ajustável entre 1 e 60, processando um parágrafo por chamada. Esse controle vale para este processo; outras instâncias e aplicações também consomem as cotas do projeto. A API considera requisições por minuto, tokens por minuto e requisições por dia; ter uma janela de contexto grande não equivale a uma cota diária. Confira os [limites ativos no AI Studio](https://ai.google.dev/gemini-api/docs/rate-limits). A fila não usa retentativas automáticas: cota esgotada (429), falhas de acesso ou conexão e respostas inválidas interrompem novos envios. As falas são preservadas. Depois de resolver o problema, aguarde o fim da fila, reaplique **Configurar IA** e solicite a análise novamente.

Somente o texto do parágrafo e as instruções de triagem são enviados. Áudio e cadastro do debate permanecem locais; informações pessoais presentes na própria fala fazem parte do texto enviado. Na camada gratuita, o Google pode usar entradas e respostas para melhorar produtos, inclusive com revisão humana, conforme seus [termos de tratamento de dados](https://ai.google.dev/gemini-api/terms#unpaid-services). A escolha do Gemini é explícita e vale até fechar o aplicativo ou aplicar outra configuração.

A integração utiliza REST com saída JSON estruturada e as mesmas validações locais de citações e campos. Cada resultado registra modelo, provedor e contagem de tokens informada pela API. O cancelamento impede novos envios e a persistência de respostas tardias; uma requisição já transmitida pode continuar sendo processada pelo Google e consumir cota. A integração não ativa ferramentas de busca: a disponibilidade de uma camada gratuita para geração de texto não garante pesquisa web gratuita. Identificação de afirmações continua sendo uma etapa anterior à busca de evidências e à revisão editorial.

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
| review.sqlite3 | Cadastro atual, revisões, triagem de afirmações, estados e histórico auditável. |

O modelo contínuo ocupa aproximadamente 682 MB e é baixado para **models** na primeira preparação, com revisão fixada no código. Após o download, a transcrição usa os arquivos locais. No modo contínuo, se a fila exceder dez segundos de áudio ou ocorrer uma falha do motor, a transcrição é interrompida e a prévia é limpa; a captura continua preservando o áudio, com aviso e registro de incompletude. Isso evita continuar um reconhecimento com amostras ausentes. No modo Whisper, as faixas não processadas são registradas para reprocessamento. O reconhecimento original mantém o falante indefinido; atribuições humanas pertencem às revisões.

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
.\.venv\Scripts\python.exe -m factcheck --prepare-triage-model
.\iniciar.cmd
```

**requirements.lock** fornece o backend CPU para Windows x64. Para um ambiente novo com GPU NVIDIA e driver compatível, use **requirements-gpu.lock** no comando de instalação. Essa configuração inclui o wheel CUDA e as bibliotecas NVIDIA dentro da `.venv`; não instala drivers nem altera o toolkit global. Foi verificada neste computador com RTX 5060 Laptop, driver 617.42 e runtime CUDA 13.4. A transcrição continua em CPU, e o motor de triagem tenta usar a GPU disponível. Os registros das análises indicam o processador efetivamente usado. Ao trocar um backend já instalado, recrie o ambiente ou reinstale explicitamente o wheel correspondente.

O leitor PyAV está limitado a uma versão compatível com o faster-whisper utilizado. Implementações de referência: [PyAudioWPatch](https://github.com/s0d3s/PyAudioWPatch), [sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx) e [faster-whisper](https://github.com/SYSTRAN/faster-whisper). Referência das bibliotecas NVIDIA: [instalação de runtimes por pip no Windows](https://docs.nvidia.com/cuda/cuda-installation-guide-microsoft-windows/).

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

- Os 99 testes automatizados passaram, incluindo os controles de captura e fechamento, cadastro e persistência, edição com histórico, reprodução do intervalo correto de áudio, restauração de citações, validação de números e negações e invalidação de resultados durante uma correção concorrente. A verificação de dependências também passou.
- Na versão 0.6, os testes do Gemini usam transporte simulado: verificam a requisição JSON, ausência de áudio e ferramentas de busca, citações ancoradas no texto, cancelamento, interrupção da fila após erro 429 e ausência da chave nos arquivos. A chave precisa ser configurada para validar a conexão real, a disponibilidade do modelo e a latência; esses resultados ainda não foram medidos.
- O fluxo também foi exercitado em um processo Windows real com transporte simulado: persistiu um resultado e cancelou o segundo durante a espera entre chamadas, sem novo envio nem credencial nos arquivos. A janela de configuração foi inspecionada visualmente, incluindo o campo protegido e o botão de aplicação.
- O ensaio completo da versão 0.5 usou uma fala sintética fictícia com uma declaração factual, uma promessa e uma opinião: gerou os três tipos, associou o participante informado e invalidou os itens após uma correção de atribuição. O cancelamento não acrescentou resultados tardios e manteve o áudio íntegro.
- Na comparação simultânea com transcrição de um WAV salvo, a triagem em CPU levou cerca de 46 s e a fila de transcrição chegou a 20 pacotes. Com GPU, a triagem levou cerca de 23 s e a fila chegou a dois pacotes, sem falhas registradas nem perda das amostras originais. O cancelamento da triagem nesse ensaio levou aproximadamente 0,02 s. São medidas de um trecho e desta máquina, sem garantia para outros conteúdos.
- Dois exemplos iniciais em CPU levaram cerca de 20–36 s. No primeiro ensaio com GPU, uma primeira geração levou cerca de 55 s; a seguinte levou cerca de 8 s. Uma fala sem pontuação foi processada em cerca de 15 s. Os ensaios não substituem um conjunto anotado por pessoas para medir precisão, cobertura, fidelidade e vieses.
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

Validar a transcrição e a triagem com gravações representativas e anotações humanas, corrigindo falhas antes de ampliar a automação. Em seguida, ligar afirmações bem definidas à busca de fontes e ao dossiê de evidências, mantendo revisão humana antes de qualquer divulgação. A definição editorial do piloto e seu conjunto de referência continuam no checklist.
