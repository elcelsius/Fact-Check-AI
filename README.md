# Fact-Check AI

Checagem assistida por IA em debates políticos ao vivo.

Projeto de um assistente de pesquisa para equipes humanas de checagem. Durante um debate, o sistema deverá transcrever falas, identificar afirmações verificáveis, pesquisar evidências e preparar análises preliminares para revisão editorial.

**Status:** protótipo com captura e transcrição locais, minutagem do vídeo, combinação reversível, exportação de sessões, relatório do ensaio, recuperação após interrupções, triagem local ou Gemini e dossiês com planejamento, coleta e importação de fontes institucionais, versão 0.14, de 23 de outubro de 2026. A identificação dos participantes e a escolha dos links são manuais. A busca automática na web e a avaliação editorial do piloto permanecem pendentes.

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

A proteção de fechamento também considera a triagem, a pesquisa de evidências, a exportação e os editores abertos. Confirmar o fechamento cancela as tarefas pendentes e aguarda sua finalização; os resultados já persistidos são mantidos. **Cancelar triagem**, **Cancelar pesquisa** e **Cancelar exportação** interrompem suas respectivas tarefas, com confirmação.

A captura acompanha a saída de áudio selecionada e inclui outros sons reproduzidos nela. O modo contínuo mantém o estado do reconhecimento e recebe pacotes sem sobreposição a cada **0,2 segundo**, usando Nemotron 3.5 ASR Streaming pelo sherpa-onnx, em CPU/int8 e português brasileiro. O arquivo WAV preserva o formato nativo; o motor converte o sinal para mono e reamostra internamente para 16 kHz. [Documentação do modelo contínuo](https://k2-fsa.github.io/sherpa/onnx/nemo/nemotron-streaming.html#sherpa-onnx-nemotron-3-5-asr-streaming-0-6b-560ms-int8-2026-06-11-multilingual)

O campo **Em andamento** contém uma hipótese que pode mudar ou terminar com uma palavra incompleta. Ela substitui a prévia anterior e não é gravada como transcrição definitiva. Os trechos estabilizados são salvos após a detecção de uma pausa, um limite de segmento de aproximadamente 15 segundos ou o encerramento normal. O motor usa 0,8 segundo de silêncio como um dos critérios de pausa. Esses trechos alimentam a organização em parágrafos. Estabilizado significa somente que o reconhecimento encerrou aquele segmento; a revisão humana permanece pendente.

**Pacotes de 0,2 segundo não significam palavras prontas em 0,2 segundo.** A primeira prévia depende da chegada da fala e do processamento. Os horários são estimativas do reconhecimento, não marcações conferidas palavra por palavra. Se o dispositivo suspender as amostras durante o silêncio, a estabilização pode aguardar novas amostras ou o encerramento.

O modo **Whisper · trechos a cada três segundos** continua disponível para comparação. Ele usa o modelo small do faster-whisper, envia o primeiro trecho após dois segundos e mantém até seis segundos de contexto. A escolha do modo acontece antes de iniciar a sessão.

### Minutagem do vídeo

Depois que uma captura começar, ou ao abrir uma sessão gravada, clique em **Minutagem do vídeo**. Informe a posição que o vídeo tinha no início efetivo da captura, após a preparação do modelo, usando **MM:SS** ou **HH:MM:SS**. Por exemplo, se a captura começou em **12:30**, um parágrafo aos **30 s** da sessão aparece em **13:00** no vídeo.

A referência pode ser salva durante a gravação e é exibida nos parágrafos, na revisão das falas, nos detalhes das afirmações e nos dossiês internos. A revisão mostra colunas separadas para o intervalo da captura e o do vídeo; a reprodução do áudio continua usando os tempos originais. A referência é uma correspondência manual e aproximada, sem leitura automática do player. Se pausar, retroceder ou avançar o vídeo, inicie outra sessão para manter a correspondência.

**Salvar referência** grava a configuração somente naquela sessão. **Limpar campo** seguido de **Salvar referência** remove a correspondência; **00:00** representa uma referência válida no início do vídeo. A configuração atual e seu histórico ficam no **review.sqlite3**, são recuperados ao reabrir e não são herdados por novas capturas. Os arquivos originais de áudio, transcrição e metadados permanecem preservados. Ajustar apenas a referência não modifica as falas nem invalida a triagem e a decisão factual; alterações concorrentes da configuração são rejeitadas para evitar sobrescritas.

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

### Combinar e descombinar na revisão

Na aba **Revisar falas**, selecione um parágrafo e clique em **Combinar com o próximo**. A prévia reúne seu texto atual ao do parágrafo imediatamente abaixo, preservando as correções humanas. Os dois precisam estar concluídos e sem atualização pendente da origem; a operação também funciona durante uma captura. Falas atribuídas a participantes diferentes não podem ser combinadas. Se algum participante estiver indefinido, é necessário confirmar que os trechos pertencem à mesma pessoa; essa confirmação não identifica automaticamente quem fala.

Clique em **Combinar trechos** para criar o parágrafo marcado como **Combinado**. Os componentes saem da lista ativa, permanecem no banco e podem ser recuperados. É possível combinar o resultado com o próximo parágrafo novamente. **Ouvir trecho**, após encerrar a captura, reproduz o intervalo completo entre o início e o fim do combinado, incluindo as pausas; a minutagem de referência continua funcionando.

**Descombinar** desfaz a última combinação e restaura os dois componentes com novas revisões. Se houve edição, atribuição ou conferência do combinado, abre-se uma tela para distribuir o texto entre os componentes e confirmar a conferência. A separação exige preservar todas as palavras e sua ordem, desconsiderando diferenças de espaços. Se o participante foi alterado no combinado, ele será atribuído aos dois textos restaurados, que ficam com revisão humana pendente. **Cancelar** mantém o combinado e suas correções.

Se uma atualização do reconhecimento mudar a origem, o combinado fica pendente de reconciliação e sua análise é bloqueada. Use **Descombinar** para conferir os textos atuais; as versões originais mais recentes são preservadas. Nas combinações sucessivas, desfazer retorna uma etapa por vez.

Combinar e descombinar invalidam as análises e os dossiês afetados, mantendo decisões anteriores no histórico. Desfazer não revalida automaticamente uma análise antiga. A operação não inicia outra chamada à IA: confira a fala e use **Analisar seleção** quando desejar nova triagem. As novas afirmações e os dossiês identificam os parágrafos de origem.

O agrupamento editorial e seu histórico ficam no **review.sqlite3** e são recuperados ao reabrir. A aba **Captura e transcrição** e os arquivos TXT/JSONL continuam mostrando o reconhecimento original; o áudio não é reescrito. Use a aba **Revisar falas** para consultar os agrupamentos e as correções atuais.

### Exportar a sessão em JSON e CSV

Na aba **Revisar falas** ou **Afirmações para checagem**, clique em **Exportar sessão**. Escolha o formato e use **Escolher arquivo e exportar**:

| Formato | Conteúdo |
| --- | --- |
| JSON completo | Cadastro, identidade da sessão, referência do vídeo, falas, origens das combinações, afirmações, dossiês e texto extraído das fontes. |
| CSV · falas | Texto atual e reconhecido, participante informado, tempos, origem, combinação e estados de transcrição e triagem. |
| CSV · afirmações | Citação, resumo, contexto, categoria, recortes, fontes e campos separados para análise preliminar e decisão humana. |
| CSV · fontes | URL, instituição, autoria, datas, forma de aquisição, hashes, avisos e localizadores. O texto extraído completo acompanha o JSON. |
| Relatório do ensaio · JSON | Contagens, denominadores, tempos registrados, tentativas históricas, avisos e limitações, em formato próprio. |
| Relatório do ensaio · TXT | As mesmas métricas em texto para leitura e comparação entre ensaios. |

O destino inicial é a subpasta **exports** da sessão. Dentro da pasta da sessão, a gravação fica restrita a essa subpasta para preservar os arquivos originais. Você pode escolher outro diretório. A operação grava em segundo plano. As exportações de registros usam uma transação e permitem continuar a captura e a revisão; os relatórios de ensaio exigem encerrar a captura e leem o banco em uma transação e os arquivos de captura separadamente. O campo provisório e as alterações ainda abertas nos editores ficam fora desses retratos.

Por padrão, são incluídas as falas atuais, mesmo com conferência humana pendente, e as afirmações ligadas à versão atual, incluindo opiniões e promessas. **Incluir itens substituídos, descartados e desatualizados** acrescenta esses registros com estado explícito. O JSON também inclui os componentes necessários para explicar uma combinação em **origin_paragraphs**. Esses componentes servem à rastreabilidade e não são novas falas ativas. O histórico integral das revisões e das fontes retiradas permanece no banco da sessão.

Os CSVs usam **UTF-8 com BOM**, separador **ponto e vírgula** e campos entre aspas. Textos que podem iniciar fórmulas recebem uma tabulação de proteção; o JSON mantém o texto literal. O comportamento de planilhas varia e a proteção não é universal, conforme a [orientação da OWASP sobre CSV Injection](https://community.owasp.org/attacks/CSV_Injection). Para integração que dependa do texto exato, use JSON. A abertura real em Excel ou Google Sheets ainda precisa de validação operacional.

**Cancelar exportação** exige confirmação. O arquivo escolhido só é substituído após a escrita completa, usando um temporário no mesmo diretório; falhas ou cancelamento anteriores à substituição preservam o arquivo existente. Fechar o aplicativo com exportação ativa também pede confirmação e aguarda o encerramento da tarefa. A exportação é local e destinada à revisão interna.

#### Contrato de exportação · versão 1

| Campo no JSON | Significado |
| --- | --- |
| format / schema_version | `factcheck-session` e versão numérica do formato. |
| event.event_id / session_id | Identidades persistentes do cadastro do evento e da captura. Editar o cadastro preserva sua identidade; uma nova captura tem outra identidade de sessão. |
| record_id | Identificador estável por registro, composto pela sessão, tipo e identificador local. Permite reconhecer o mesmo registro em outra exportação. |
| record_sha256 | Hash dos campos exportados de um registro; muda quando seu conteúdo ou estado muda. |
| content_sha256 / exported_at | Hash do retrato e horário UTC de sua cópia. O horário é excluído do hash; reexportar dados iguais na mesma versão mantém o hash. |
| paragraphs / origin_paragraphs | Falas do escopo escolhido e componentes adicionais de origem. Seus identificadores locais se relacionam dentro de `session_id`. |
| claims.source_current | A afirmação corresponde à versão atual e não foi descartada. Esse campo não classifica sua veracidade. |
| dossiers | Análise preliminar e decisão humana em campos separados, com revisão e indicadores de atualidade. |
| dossiers.plan | Pergunta, recortes, lacunas, URLs candidatas, origem e data do plano. Rascunho de IA não corresponde a conferência humana ou evidência coletada. |
| sources | Fontes associadas às afirmações incluídas, com cópia textual e localizadores. `url_access_confirmed` distingue consulta à URL de importação local ou origem não informada. |

Cada CSV repete **evento_id**, **sessao_id**, **registro_id**, **registro_sha256**, **snapshot_sha256** e o horário de exportação. A coluna **origem_atual** das afirmações indica correspondência com a versão da fala; **preliminar_atual** e **decisao_atual** informam se as conclusões exibidas ainda se aplicam. Registros históricos ficam identificados como **historical** no estado do dossiê.

Cada exportação copia os dados naquele instante. CSVs produzidos em momentos diferentes podem ter hashes de retrato diferentes durante uma captura ou revisão. O JSON reúne as tabelas do mesmo retrato. As definições de campos e a escrita dos arquivos estão em [factcheck/exports.py](factcheck/exports.py). As identidades de sessões antigas são preenchidas na abertura, sem reanalisar as falas; copiar a pasta completa com o SQLite preserva essas identidades.

### Relatório do ensaio

Encerre a captura, abra **Exportar sessão** e escolha **Relatório do ensaio · TXT** para leitura ou **Relatório do ensaio · JSON** para processar as métricas. A tarefa usa a mesma confirmação de cancelamento e proteção de fechamento das demais exportações. O seletor de itens históricos fica desabilitado: o relatório separa as contagens atuais das tentativas históricas automaticamente.

O resumo apresenta parágrafos ativos, conferência humana, participante indefinido, triagem concluída, categorias identificadas e pendências de fontes, análise preliminar e decisão humana. A proporção de decisões humanas usa como denominador **somente as afirmações factuais identificadas pela IA e ainda atuais**. Ela não representa precisão nem cobertura das afirmações presentes no vídeo. Combinações, descartes e correções não contam as versões antigas como afirmações atuais.

Nas novas capturas, o log registra o tempo até a primeira prévia e a entrega dos segmentos estabilizados, sem repetir o texto nesses eventos. O relatório distingue esses tempos do processamento e atraso dos pacotes. Mediana acompanha o número de observações válidas; P95 usa interpolação linear a partir de 20 observações. Tempos ausentes ou inválidos ficam indisponíveis ou são contados como excluídos. Uma gravação antiga não recebe uma estimativa inventada de primeira prévia. O tempo até a decisão humana inclui esperas e não mede esforço de revisão.

O formato do relatório JSON é **factcheck-session-report**, versão **1**; ele não substitui o JSON completo da sessão. Inclui hashes do relatório e dos registros agregados, sem copiar falas, conteúdo das fontes, mensagens livres de erro ou chaves da API. A geração é local e não inicia IA, pesquisa ou publicação. Precisão, cobertura contra referência humana e erro de transcrição permanecem **não avaliados**. Consulte o [guia do ensaio](docs/operacao-e-recuperacao.md#ensaio-editorial-com-gravação).

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

O banco **review.sqlite3** guarda o cadastro atual, originais, revisões humanas, análises, afirmações, cópias extraídas das fontes e dossiês com histórico. Os arquivos de transcrição e parágrafos preservam o reconhecimento original; o texto corrigido aparece na aba de revisão e no banco. A identificação automática de quem fala e a busca automática de links continuam pendentes.

### Retomar uma sessão interrompida

Em **Revisar falas → Abrir sessão gravada**, selecione a pasta da sessão e use **Estado da sessão**. A tela informa interrupção, falas salvas, parágrafos sem encerramento, tarefas interrompidas e dados de áudio presentes. A abertura mantém as correções humanas e não reinicia chamadas à IA ou pesquisas. Uma captura ainda pertencente a processo ativo bloqueia a abertura como sessão gravada.

Uma última linha JSONL incompleta, sem quebra final, gera aviso e permanece no arquivo original. Corrupção intermediária bloqueia a importação. **Encerrar parágrafos pendentes** pede confirmação, usa somente o texto existente e mantém a conferência humana pendente. O encerramento tem revisão e histórico próprios e aparece nas exportações.

Se o WAV padrão do capturador ficou com cabeçalho incompleto, **Criar cópia recuperada do áudio** preserva as amostras completas disponíveis em `recovered/`. A operação ocorre em segundo plano, pode ser cancelada com confirmação e preserva o original. **Ouvir trecho** usa a cópia concluída, inclusive após reabrir. A duração encontrada não garante cobertura integral da fala; dados provisórios ou ainda não gravados podem ter sido perdidos.

Para voltar à transmissão, inicie outra captura e confira a nova minutagem. Sessões antigas sem identificação do processo ficam com estado não confirmado e reparos bloqueados. Consulte o [procedimento de operação e recuperação](docs/operacao-e-recuperacao.md), incluindo o ensaio técnico repetível e a ficha para testar com vídeo real.

### Usar a API Gemini como alternativa

O modo inicial continua sendo **Local** em cada abertura do aplicativo. Para usar a API:

1. Crie uma chave no [Google AI Studio](https://aistudio.google.com/api-keys). Para usar somente a camada gratuita, escolha um projeto sem faturamento ativado e confira suas cotas.
2. Antes de iniciar uma captura, clique em **Configurar IA · API Google**, selecione **Gemini API** e cole sua chave no campo **Sua chave da API Google (Gemini)**. Cada usuário pode informar sua própria chave diretamente no aplicativo. O campo começa oculto; **Mostrar/Ocultar** permite conferir a digitação e **Limpar** apaga o conteúdo antes de aplicar. Também é possível definir **GEMINI_API_KEY** ou **GOOGLE_API_KEY** no ambiente antes de abrir o aplicativo.
3. Opcionalmente, clique em **Testar conexão**. O aplicativo faz uma chamada ao modelo configurado usando somente texto fictício, sem enviar falas, documentos ou cadastro do debate. O teste consome cota do seu projeto e não consulta faturamento nem saldo disponível. Ele valida a autenticação e uma resposta JSON simples naquele momento; não garante qualidade da checagem nem disponibilidade futura.
4. Confira o aviso sobre envio de texto e clique em **Aplicar configuração**. Testar a chave não aplica a configuração automaticamente. A chave digitada fica apenas na memória desta execução, sem ser gravada pelo aplicativo em configurações, sessões, logs ou Git. Ela precisa ser informada novamente após fechar, salvo quando fornecida pelo ambiente.
5. Analise uma fala ou inicie uma captura com identificação automática. Para comparar uma fala já analisada pelo motor local, use **Analisar seleção**, que solicita nova análise da revisão atual.

Durante o teste, o mesmo botão permite **Cancelar teste**. Alterar a chave cancela o teste anterior; uma resposta antiga não valida a chave nova. Fechar a configuração também cancela seu teste, e o fechamento do aplicativo aguarda a confirmação das atividades pendentes. Uma requisição já transmitida pode continuar sendo processada pelo Google e consumir cota, mesmo após cancelar. As mensagens distinguem erros de acesso/cota e causas de rede, como DNS, certificado TLS, tempo limite e bloqueio pelo Windows; nenhuma resposta bruta com credenciais é exibida. Consulte o [guia oficial de solução de problemas](https://ai.google.dev/gemini-api/docs/troubleshooting).

O modelo configurado é **gemini-3.1-flash-lite**, cuja entrada e saída de texto têm camada gratuita na [tabela oficial consultada em 22/10/2026](https://ai.google.dev/gemini-api/docs/pricing#gemini-3.1-flash-lite). A disponibilidade e as cotas dependem do projeto. O aplicativo não consulta o estado de faturamento e não pode garantir custo zero em um projeto com cobrança habilitada. Não ativa faturamento, não troca de modelo e não muda de provedor automaticamente.

A fila começa com espaçamento de **5 chamadas por minuto**, ajustável entre 1 e 60, processando um parágrafo por chamada. Esse controle vale para este processo; outras instâncias e aplicações também consomem as cotas do projeto. A API considera requisições por minuto, tokens por minuto e requisições por dia; ter uma janela de contexto grande não equivale a uma cota diária. Confira os [limites ativos no AI Studio](https://ai.google.dev/gemini-api/docs/rate-limits). A fila não usa retentativas automáticas: cota esgotada (429), falhas de acesso ou conexão e respostas inválidas interrompem novos envios. As falas são preservadas. Depois de resolver o problema, aguarde o fim da fila, reaplique **Configurar IA** e solicite a análise novamente.

A triagem envia o texto do parágrafo e suas instruções. Ao solicitar **Analisar com Gemini** no dossiê, são enviados também o participante informado, a data do debate e os trechos selecionados das fontes, com seus metadados. O áudio permanece local; informações pessoais presentes no material fazem parte do texto enviado. Na camada gratuita, o Google pode usar entradas e respostas para melhorar produtos, inclusive com revisão humana, conforme seus [termos de tratamento de dados](https://ai.google.dev/gemini-api/terms#unpaid-services). A escolha do Gemini é explícita e vale até fechar o aplicativo ou aplicar outra configuração.

A integração utiliza REST com saída JSON estruturada e as mesmas validações locais de citações e campos. Cada resultado registra modelo, provedor e contagem de tokens informada pela API. O cancelamento impede novos envios e a persistência de respostas tardias; uma requisição já transmitida pode continuar sendo processada pelo Google e consumir cota. A integração não ativa ferramentas de busca: a disponibilidade de uma camada gratuita para geração de texto não garante pesquisa web gratuita. Identificação de afirmações continua sendo uma etapa anterior à busca de evidências e à revisão editorial.

### Pesquisar fontes e revisar um dossiê

1. Na aba **Afirmações para checagem**, selecione um item e clique em **Abrir dossiê**.
2. Confira ou edite uma das consultas sugeridas e use **Buscar no navegador**. As consultas procuram dados, metodologia e divergências em fontes institucionais. Abrir a consulta é registrado no histórico; os resultados não são coletados automaticamente.
3. Escolha a página original ou o PDF pertinente, copie sua URL para o campo da aba **Dossiê e fontes** e clique em **Coletar fonte**. A coleta aceita HTTPS em **gov.br, jus.br, leg.br, who.int, worldbank.org, imf.org, oecd.org e un.org**, inclusive subdomínios. A inclusão na coleção institucional não comprova uma declaração.
4. Selecione um documento e use **Ler cópia extraída** ou **Abrir fonte**. Confira autoria, publicação, território, período, indicador, metodologia e se o conteúdo já estava disponível na data do debate. Fontes que reproduzem a mesma origem não devem ser contadas como confirmações independentes.
5. Com Gemini configurado, **Analisar com Gemini** solicita uma análise preliminar dos documentos coletados. Sem chave, é possível coletar, ler, registrar a decisão humana e exportar normalmente. A análise utiliza até 24 trechos, totalizando 24.000 caracteres, selecionados por correspondência de termos; não há garantia de selecionar todos os trechos relevantes.
6. Use **Registrar decisão humana** para informar responsável, classificação e justificativa. Uma decisão confirmada ou contradita exige fonte coletada e a confirmação de que os recortes foram conferidos. **Inconclusiva** permite registrar a insuficiência de evidências. O nome informado é uma atribuição local, sem autenticação de revisores neste protótipo.
7. **Exportar dossiê interno** grava um Markdown com fala, contexto, fontes, trechos, hashes, análise preliminar, decisão humana e estados de pesquisa. A exportação não publica nem envia o documento a terceiros. Cópias exportadas não são atualizadas se o dossiê mudar depois.

Se a coleta online falhar, ou se você já tiver o material, informe a URL institucional de origem e use **Importar PDF/HTML** para selecionar uma cópia já baixada. A leitura do arquivo e a extração funcionam sem rede e sem chave Gemini. O arquivo original não é alterado. O dossiê guarda o texto extraído e seu hash, o nome do arquivo e a data de importação; o arquivo binário não é arquivado. Permanecem os mesmos limites de tamanho, extração e quantidade de fontes.

Uma cópia importada fica identificada no painel, no dossiê, na exportação e no material enviado à análise como **fornecida pelo operador**. A URL é uma informação declarada, sem consulta pelo aplicativo; a data de importação não é apresentada como data de acesso à URL. Cabe ao revisor conferir que o arquivo corresponde à fonte informada. A análise automática fica **inconclusiva** quando depende de uma citação de cópia importada cuja origem online ainda não foi conferida. A decisão humana pode registrar sua avaliação com justificativa após consultar a fonte. Uma coleta online posterior dos mesmos bytes atualiza a origem da cópia e exige nova revisão; importar os mesmos bytes de uma fonte já coletada online não rebaixa o registro existente.

As citações da IA precisam existir literalmente nos blocos enviados, com documento e localizador conhecidos. Citações que cortam palavras, números ou omitem uma negação imediatamente anterior são recusadas. Ausência de suporte, recortes indefinidos ou evidências classificadas como conflitantes rebaixam uma conclusão automática para **inconclusiva**. Essas verificações não comprovam o significado da fonte nem a conclusão; a revisão humana continua necessária.

Cada documento preserva a cópia textual extraída, URL solicitada e final, autoria e publicação quando identificadas, acesso, extrator e sua versão, hash do material recebido e localizadores. HTML usa números da cópia extraída; PDF usa página e trecho. O arquivo binário original não é arquivado. A leitura é limitada a **8 MB**, **40 páginas de PDF** ou **120.000 caracteres extraídos**, com até **seis fontes ativas por dossiê**. PDFs escaneados precisam de OCR, ainda não implementado. Tabelas complexas, páginas dinâmicas, documentos protegidos e bloqueios de acesso podem impedir a leitura ou perder estrutura; nesses casos, consulte a fonte e as limitações registradas.

Uma nova versão da mesma URL substitui a cópia ativa e preserva a anterior no histórico. **Retirar fonte** exige justificativa e mantém a cópia no histórico. Alterar evidências ou gerar nova análise invalida a decisão humana anterior. Mudanças na fala ou no cadastro do debate tornam o dossiê antigo desatualizado; resultados tardios não são aplicados a outra revisão. As evidências e decisões anteriores continuam auditáveis no SQLite.

A coleta não utiliza cookies, login ou execução de JavaScript. Cada URL e redirecionamento passa pela lista de domínios e validação de endereços públicos; a conexão TLS usa os endereços validados e verifica o hostname. I/O de pesquisa roda em thread e extração HTML/PDF em processo separado; o cancelamento bloqueia a persistência de resultados tardios. Uma operação de rede já iniciada pode continuar até retornar ou expirar. Cada tarefa tem limite de 90 segundos, sem retentativa automática. A análise de evidências é solicitada individualmente; suas chamadas também consomem a cota do projeto Gemini, além da fila de triagem.

No ambiente gerenciado de desenvolvimento, as tentativas de coleta integrada receberam **WinError 10013**, bloqueio de socket do Windows. Portanto, o acesso pela interface ainda precisa ser validado ao abrir normalmente **iniciar.cmd**. Falhas ficam visíveis e não geram evidência fictícia. A importação local permite continuar a revisão sem essa conexão e foi exercitada com extração em processo Windows real. Os testes de API usam transporte simulado; chamadas reais ao Gemini continuam pendentes de chave e podem ser verificadas com **Testar conexão**.

### Planejar a checagem

Abra uma afirmação em **Dossiê e fontes** e clique em **Planejar checagem**. Registre a pergunta, o período, o território, o indicador ou fato a demonstrar, a comparação e as lacunas. A situação pode ser **pergunta definida para pesquisar**, **falta contexto ou recorte** ou **possível extração sem alegação verificável**. Campos vazios continuam a definir, sem recuperar suposições antigas do modelo nas sugestões de busca.

As URLs institucionais candidatas são indicações para pesquisa. Salvá-las não consulta a rede nem as inclui como evidências; use **Coletar fonte** ou **Importar PDF/HTML** para arquivar conteúdo. O plano identifica **rascunho de IA** ou **plano salvo pelo operador**. Nenhum dos dois confere a transcrição, confirma fatos, altera a categoria extraída ou descarta automaticamente uma afirmação. Depois de conferir o áudio, uma extração indevida pode ser descartada com justificativa na fila.

O planejamento tem revisão e histórico próprios no dossiê. Uma mudança invalida a análise e a decisão atuais, preserva fontes e histórico e rejeita resultados da versão anterior ainda em processamento. Salvar os mesmos dados não desfaz uma decisão posterior. Alterações concorrentes são rejeitadas; cancelar ou fechar um editor alterado pede confirmação. A coleta, a análise posterior e a retirada de fontes preservam o plano.

O plano acompanha o dossiê interno e o JSON da sessão; o CSV de afirmações acrescenta as colunas **plano_***. O relatório resume planos de extrações atuais, inclusive indefinidas, sem mudar o denominador das afirmações factuais. Na análise Gemini, um plano marcado como falta de contexto, possível extração não verificável ou rascunho de IA mantém o resultado automático inconclusivo. A decisão humana continua separada.

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
| review.sqlite3 | Cadastro atual, referência manual do vídeo, revisões, triagem de afirmações, estados e histórico auditável. |

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
.\.venv\Scripts\python.exe -m scripts.rehearse_recovery
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Para escolher uma saída pela linha de comando, acrescente **--device** com o índice informado pela listagem. **--engine streaming** é o padrão; **--model tiny|base|small** se aplica ao modo Whisper. **--paragraph-pause 1.5** configura a pausa sugerida entre parágrafos. Os testes verificam preservação de amostras, formato WAV, medição de nível, horários, união das janelas, substituição das prévias, organização em parágrafos, encerramento, falhas e cancelamento. As gravações, modelos, caches e logs são ignorados pelo Git.

**paragraphs.jsonl** é um histórico de atualizações: para obter o estado atual, selecionar a maior **version** de cada **paragraph_id** dentro da sessão. O campo **closed** indica que o agrupamento foi encerrado, e **end_reason** distingue conclusão, cancelamento e interrupção; isso não equivale a validação editorial.

### Validação realizada neste computador

- Os 270 testes automatizados passaram, incluindo os controles de captura e fechamento, cadastro e persistência, edição com histórico, reprodução do intervalo correto de áudio, restauração de citações, validação de números e negações e invalidação de resultados durante uma correção concorrente.
- Na versão 0.14, quatro planos foram preparados em uma nova cópia da gravação, com conferência humana pendente. A orientação de triagem foi atualizada e a gramática local passou a exigir conteúdo nos campos de citação, resumo e justificativa. A nova execução concluiu dois dos três trechos; o primeiro permaneceu rejeitado por citação não literal. A extração genérica de pedido de explicação passou de factual para indefinida, e a alegação percentual foi extraída como fato a pesquisar; isso não estabelece melhora geral de precisão. Uma página oficial do [MJSP sobre dados nacionais](https://www.gov.br/mj/pt-br/assuntos/sua-seguranca/seguranca-publica/estatistica) foi efetivamente coletada, com 23 blocos extraídos, como referência metodológica. A coleta do TSE falhou com PermissionError e ficou apenas como candidata. Nenhuma API de IA foi chamada e nenhum fato foi aprovado. Os testes cobrem origem dos planos, campos vazios, concorrência, invalidação, preservação de fontes, exportação, análise simulada e cancelamento do editor; a tela foi inspecionada com dados fictícios.
- Na versão 0.13, o relatório foi exercitado em uma cópia de gravação existente com **336,341 s de áudio e 22 parágrafos**, sem alterar os originais. Uma execução adicional da triagem local nos três primeiros parágrafos concluiu dois e rejeitou um por citação inválida; gerou oito itens, dos quais três factuais, todos ainda sem fontes ou decisão humana. Nenhuma fala foi enviada a API. O ensaio verifica execução e registro das pendências, sem avaliar precisão. Testes cobrem denominadores, versões antigas, agrupamentos, log parcial, tempos inválidos, ausência de referência humana, concorrência, escrita real dos relatórios e proteção de fechamento; a interface foi inspecionada com dados fictícios.
- Na versão 0.12, um subprocesso próprio com dados fictícios foi encerrado à força: a recuperação reverteu uma transação SQLite não confirmada e preservou revisão humana, decisão do dossiê e os 2,4 s de PCM disponíveis. Foram conferidos aviso de cauda incompleta, tarefas interrompidas, encerramento manual, exportação e reabertura repetível. Outros testes cobrem reparo de cabeçalho em cópia, amostra incompleta, cancelamento, mudança do arquivo durante a cópia e fechamento da interface. A tela de estado foi inspecionada com dados fictícios. O ensaio não usa ASR ou rede e não valida queda de energia nem qualidade editorial; consulte o [procedimento](docs/operacao-e-recuperacao.md).
- Na versão 0.11, os testes exercitam a escrita real de JSON/CSV, os identificadores persistentes, reexportação, cópia de sessões, migração de bancos antigos e coerência durante uma revisão concorrente. Cobrem também opiniões, descartes, origens de combinações, preliminar e decisão humana separadas, fontes importadas, proteção de CSV, falha e cancelamento tardio preservando o arquivo anterior. A interface permite exportar durante a captura, tem confirmação de cancelamento e protege o fechamento. As telas foram inspecionadas com dados fictícios; a abertura em planilhas e o fluxo editorial real seguem pendentes de ensaio.
- Na versão 0.10, os testes cobrem combinação de blocos adjacentes e concluídos, conferência de autoria indefinida, bloqueio de participantes diferentes, preservação dos originais e correções, combinações sucessivas, reabertura, atualizações tardias e rejeição de operações desatualizadas. A separação de textos corrigidos impede omissão de palavras, incluindo negações; dossiês e resultados antigos continuam históricos. A reprodução foi conferida pelo conteúdo PCM do intervalo combinado, sem mudar o áudio original. As novas janelas e a lista de revisão foram inspecionadas com dados fictícios; a operação editorial em um debate real permanece pendente de avaliação.
- Na versão 0.9, os testes cobrem conversão e limites da minutagem, referência zero e remoção, persistência e histórico, rejeição de edição concorrente, abertura de bancos antigos e independência entre sessões. A interface foi inspecionada com dados fictícios; a reprodução mantém o intervalo original, e a alteração da referência preserva análises em andamento e decisões humanas. Essa validação não mede a precisão de sincronização com um player real.
- Na versão 0.8, os testes verificam a chamada fictícia de conexão, o limite reduzido de saída, a proteção da chave, o cancelamento, a troca da chave durante uma resposta pendente e o fechamento da configuração/aplicativo. A importação de HTML e PDF fictícios foi exercitada sem rede, com extração em processo Windows real, metadados de origem não confirmada, preservação dos arquivos originais e decisão humana separada. Outros testes cobrem arquivos inválidos ou grandes demais, atualização da origem após coleta online e rebaixamento de análise dependente de cópia importada para inconclusiva. Não houve chamada real com chave Google nesta validação.
- A configuração com **Testar conexão** e o painel com **Importar PDF/HTML** foram inspecionados visualmente em janelas descartáveis, usando somente dados fictícios e sem iniciar gravação.
- Na versão 0.7, a suíte inclui extração real das bibliotecas sobre HTML e PDF fictícios, URLs e redirecionamentos permitidos, citações literais, recortes indefinidos, revisão com concorrência de versões, retirada de fontes com histórico, exportação interna e cancelamento com resposta de rede tardia. Os números dos exemplos de teste são fictícios. O ensaio HTTP real foi bloqueado pelo ambiente; a coleta pela interface e o uso real do Gemini ainda precisam de validação operacional.
- Um ensaio da suíte executa a extração em processo Windows real, com HTML recebido por transporte simulado, prepara análise com Gemini simulado, rebaixa uma conclusão com metodologia indefinida e registra revisão humana antes da exportação. A nova aba foi inspecionada visualmente com dados fictícios, incluindo os botões de revisão e exportação.
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

O [checklist de desenvolvimento](docs/checklist-desenvolvimento.md) detalha as tarefas, dependências, responsáveis sugeridos e critérios de conclusão de cada fase. O [guia de operação e recuperação](docs/operacao-e-recuperacao.md) orienta a retomada e o registro de ensaios. Os arquivos deste repositório são a referência para acompanhar o andamento técnico.

## Premissas centrais

A equipe humana validará cada dossiê e decidirá sobre qualquer divulgação. A análise preliminar deverá apresentar evidências consultáveis, contexto e lacunas.

O primeiro piloto acompanhará um debate político ao vivo em uso interno. Um ensaio com gravação permitirá testar a operação antes do evento.

O projeto avaliará a redução de trabalho humano junto com a qualidade das evidências, a cobertura das afirmações, o tempo até a revisão e o custo. Tecnologias, orçamento, equipe, evento e metas operacionais serão definidos na preparação do piloto.

## Próximo marco

Usar **Testar conexão** para validar uma chave e o acesso real ao modelo no Windows. A coleta real foi exercitada em uma página do MJSP; ampliar a validação para outros domínios e diagnosticar a tentativa do TSE antes de generalizar disponibilidade. Cópias importadas continuam com origem pendente de conferência. Avaliar transcrição, triagem e dossiês com gravações representativas e anotações humanas. A descoberta automática de links dependerá de um provedor de busca com custo e limites conhecidos. A definição editorial do piloto e seu conjunto de referência continuam no checklist.

O [checklist de desenvolvimento](docs/checklist-desenvolvimento.md) também registra as prioridades de operação propostas em 23/10/2026. A minutagem de referência foi implementada na versão 0.9, a combinação reversível na 0.10, a exportação estruturada na 0.11, o diagnóstico de retomada na 0.12, o relatório do ensaio na 0.13 e o planejamento dos dossiês na 0.14. Os primeiros rascunhos distinguem lacunas e referências de evidências pertinentes. O próximo marco é conferir o áudio e o contexto, identificar pessoas e períodos com base no vídeo e completar a pesquisa dos casos elegíveis antes da decisão humana. Essas melhorias mantêm o aplicativo independente.
