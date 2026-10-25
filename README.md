# Fact-Check AI

Checagem assistida por IA para debates, propaganda política e noticiários.

Aplicativo Windows que transcreve falas, identifica afirmações verificáveis e organiza evidências e análises preliminares para revisão humana. Funciona com áudio da saída do computador ou ensaio silencioso de um WAV salvo.

**Status:** MVP local **0.25.0**, de 25 de outubro de 2026, com revisão humana e exportação. Este fechamento técnico acrescenta inclusão e divisão manual de afirmações, citações e cálculos reproduzíveis, pesquisa sequencial por prioridade, pausa de captura com lacunas identificadas, limites de API, avaliação com referência humana e backup/restauração. Consulte a [entrega e seus limites](docs/entrega-mvp-local.md). Avaliação editorial com material real, chamadas com as chaves do usuário e piloto representativo permanecem abertos. Contas e operação simultânea são evolução posterior. A [comparação CPU/NVIDIA](docs/desempenho-transcricao.md) continua disponível; picos de atraso precisam ser considerados no ensaio.

### Controles do fechamento local

| Onde | O que fazer |
| --- | --- |
| Captura | **Pausar · ignorar áudio** marca o intervalo e grava silêncio; **Retomar captura** volta a receber áudio. O vídeo continua no player. |
| Revisar falas | **Incluir afirmação** cria um recorte literal com justificativa, mesmo quando a IA não o selecionou. |
| Afirmações para checagem | **Dividir afirmação selecionada** preserva o original como histórico; as partes começam sem evidências ou decisão. **Pesquisar fila visível** executa casos selecionados com plano conferido e limites explícitos. |
| Dossiê e fontes | **Registrar evidências e cálculos** permite selecionar citações de documentos coletados, registrar contas e anotar período, anterioridade e origem comum das fontes. |
| Operação e avaliação | Configure tentativas de API e preços de referência, cadastre referências humanas, calcule métricas e crie ou restaure uma cópia `.fcbak` da sessão. |

O [guia operacional](docs/operacao-e-recuperacao.md#controles-da-versão-025) detalha os novos controles. Fontes e cálculos registrados pelo operador continuam sujeitos à revisão factual. Sem referências humanas anotadas, o aplicativo não informa precisão ou cobertura presumidas. Nenhuma dessas ações publica conteúdo.

## Diagramas de funcionamento

Os dois diagramas são arquivos SVG editáveis, que podem ser abertos no navegador e ampliados sem perda de qualidade:

- [Fluxo interno do sistema](docs/diagramas/fluxo-interno.svg): captura, transcrição, tarefas de IA, validação, persistência, evidências e decisão humana.
- [Jornada do usuário](docs/diagramas/fluxo-usuario.svg): preparar a captura, conferir falas, organizar a fila, pesquisar e concluir a revisão.

As caixas tracejadas identificam evolução posterior: descoberta autônoma contínua, vozes durante a transmissão e operação simultânea em equipe. A pesquisa em fila iniciada pelo operador e a separação de vozes após gravar estão disponíveis. Os fluxos mostram possibilidades de uso; captura, triagem e pesquisa podem ocorrer em paralelo. A exportação interna pode conter pendências identificadas. Qualquer divulgação continua sob responsabilidade editorial humana. Consulte a [legenda e a regeneração dos diagramas](docs/diagramas/README.md).

## Usar o aplicativo

No Windows, abra **iniciar.cmd** com dois cliques. Na janela:

1. Em **Dados da transmissão**, escolha o tipo de conteúdo e cadastre título, data da fala, origem do vídeo e participantes. O cadastro é opcional para um teste rápido.
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

O modo **Whisper · CPU · trechos a cada três segundos** continua disponível para comparação. A versão 0.24 acrescenta **Whisper · NVIDIA (GPU) · trechos a cada três segundos**, com o mesmo modelo small e preparação antes da captura. Os dois enviam o primeiro trecho após dois segundos e mantêm até seis segundos de contexto. A escolha acontece antes da sessão. Consulte [resultados, instalação e limites](docs/desempenho-transcricao.md); somente o motor contínuo fornece a prévia revisável.

### Ensaiar uma gravação e conferir vozes

Para material já gravado, clique em **Ensaiar WAV salvo** e selecione um WAV PCM16, de 8 a 192 kHz. O aplicativo cria outra sessão e recebe as amostras no ritmo original, silenciosamente e sem dispositivo físico. O fim do arquivo encerra e salva; cancelar exige confirmação. O original permanece intacto. Também é possível usar `python -m factcheck --replay-wav caminho.wav`.

Depois de encerrar a captura, abra **Falantes → Preparar modelos locais**. O download explícito de aproximadamente 47 MB é conferido por SHA-256; depois, a análise funciona localmente e sem API. Informe a quantidade de vozes esperadas ou zero para estimar e use **Analisar gravação**. Os números **Voz 1, Voz 2...** pertencem somente àquela análise e não identificam pessoas pelo nome.

Selecione trechos da mesma voz usando Ctrl/Shift, ouça-os individualmente e clique em **Atribuir participante à seleção**. Escolha um nome cadastrado, confirme que ouviu todos os trechos e justifique. Substituir outro participante exige confirmação adicional. Mistura de vozes, pouca fala, origens pendentes e edições antigas impedem atribuição em lote; nesses casos, use **Revisar fala**. A cobertura temporal mostrada não é confiança estatística.

A atribuição registra a proveniência, aumenta a revisão da fala e exige nova triagem. Não confere o texto nem decide a veracidade. **Cancelar análise / preparação** e o fechamento durante a tarefa pedem confirmação. Consulte os modelos e resultados na [entrega local](docs/entrega-mvp-local.md#falantes-alcance-e-privacidade).

No ensaio da 0.23, processar 20,011 segundos com o motor contínuo levou 33,42 segundos de computação isolada em CPU. Na comparação do fluxo completo da 0.24, o contínuo e Whisper em CPU consumiram cerca de 40 segundos de inferência; Whisper com NVIDIA, 12,88 segundos. A preparação é medida separadamente. O teste NVIDIA de 336,341 segundos terminou sem perda de PCM, mas teve picos de atraso. Meça o desempenho e a fidelidade antes de um evento; os resultados da 0.3 abaixo descrevem outras execuções.

### Configurar temas para triagem e revisão

Abra **Temas → Novo tema**, antes ou depois de uma captura. Cadastre um nome de até 100 caracteres, até doze variações de escrita separadas por ponto e vírgula, descrição opcional de até 1.500 caracteres e um motivo obrigatório de até 2.000 caracteres. Não há uma lista editorial imposta pelo aplicativo: a equipe prepara seus próprios temas. Exemplo de cadastro fictício: **Saúde pública**, com os termos associados **SUS** e **Saúde coletiva**. A equipe precisa conferir se esses agrupamentos são adequados ao piloto.

**Buscar** combina palavras do nome, variações e descrição, ignorando maiúsculas e acentos. **Editar tema**, **Arquivar tema** e **Restaurar tema** preservam versões, justificativas e histórico. Nomes e variações normalizados pertencem a um único tema, inclusive entre arquivados; para liberar um termo, revise explicitamente o cadastro que o contém. Editar um arquivado não o restaura. Uma edição antiga é rejeitada se o mesmo tema tiver mudado em outra janela.

O vocabulário atua **depois da resposta da IA**, por correspondência textual completa com nome ou variação cadastrada, ignorando caixa, acentos e espaços. Não modifica os prompts, não envia as descrições ao Gemini e não acrescenta chamadas ou tokens. A IA continua sugerindo um tema livre. Uma sugestão conhecida recebe o nome cadastrado; o termo originalmente sugerido fica preservado. Um termo desconhecido permanece como foi informado e aparece como **Fora do vocabulário**; não há inferência por palavras soltas, sinônimos não cadastrados ou significado. Tema ausente continua sem tema.

Cada parágrafo recebe uma cópia do vocabulário **ao entrar na fila de triagem**. Mudanças posteriores valem para as próximas entradas; tarefas já enfileiradas usam a versão capturada, inclusive após esperar na fila. A análise e as afirmações registram identidade, revisão e impressão digital do vocabulário. A afirmação também guarda o tema/versão correspondente e o termo original. Isso funciona com triagem local e Gemini, sem alterar citação, categoria ou decisão factual. Para reprocessar um trecho já analisado com novos temas, solicite nova triagem explicitamente.

Em **Afirmações para checagem → Revisar afirmação**, o campo **Tema** sugere os nomes ativos e também aceita texto livre. Salvar aplica a mesma correspondência textual e identifica a origem como revisão do operador. Se o vocabulário mudar enquanto a revisão estiver aberta, reabra o editor para conferir as sugestões atuais. Como nas outras revisões da extração, salvar pode invalidar conclusões dependentes e pedir nova conferência do plano; a justificativa é obrigatória. O resultado automático, inclusive seu tema e a normalização original, fica preservado no histórico.

Alterar ou arquivar temas no cadastro não reescreve falas, afirmações, decisões, prioridades, responsáveis ou a coleção de fontes. Filtros continuam usando o tema efetivamente salvo em cada afirmação; cadastros e sessões antigas mantêm os temas livres até uma revisão ou triagem explícita. Este incremento não renomeia em lote os temas das referências da coleção ou dos antecedentes consultados. O detalhe da afirmação e o dossiê mostram a organização temática separada da verificação factual.

O cadastro e seu histórico ficam em **library/topics.sqlite3**, compartilhados entre as sessões da mesma pasta do aplicativo e ignorados pelo Git. Para backup ou transferência, feche o aplicativo e copie a pasta **library**, além das sessões necessárias. Sem esse arquivo, a triagem mantém temas livres com indicação de vocabulário não configurado. Um arquivo presente mas inválido ou indisponível impede novas entradas na triagem até a conferência do cadastro; a captura e os registros já salvos continuam disponíveis. Não há migração ou reparo automático desse arquivo durante a triagem.

O JSON inclui `claims[].topic_annotation`, a versão automática preservada quando houver revisão e `engine.topic_vocabulary` com identidade/revisão/impressão digital. A definição copiada contém apenas o tema usado, não o restante do vocabulário privado. O CSV de afirmações acrescenta estado temático, termo original, origem da normalização e identificadores/revisões de tema e vocabulário. O dossiê descreve esses dados; uma correspondência temática não aprova a extração nem confere a veracidade. Registros antigos sem essa informação não recebem procedência inventada.

### Preparar uma coleção de fontes

A aba **Coleção de fontes** funciona antes da captura e sem chave de API. Ela mantém referências de pesquisa compartilhadas entre as sessões da mesma pasta do aplicativo. Clique em **Nova referência** e cadastre título, URL institucional HTTPS, instituição informada e até oito temas, separados por ponto e vírgula. Informe também periodicidade, metodologia, limites de uso e observações quando conhecidos. Campos metodológicos vazios permanecem **A definir**. O motivo do cadastro ou alteração é obrigatório.

Use **Buscar** para combinar palavras do cadastro, ignorando maiúsculas e acentos, e **Tema** para selecionar um tema exato. A busca inclui título, URL, instituição, temas e notas metodológicas. Ela usa os registros já carregados e não consulta a web. **Editar referência**, **Arquivar referência** e **Restaurar referência** preservam versões e motivos. Arquivadas ficam ocultas até marcar **Incluir arquivadas**. A mesma URL normalizada só pode ter um cadastro, inclusive entre as arquivadas; use vários temas para classificá-la.

Para usar uma referência num caso, abra a afirmação em **Dossiê e fontes**, clique em **Coleção de fontes**, selecione um item ativo e use **Usar URL no dossiê**. O destino aparece na tela. A operação registra uma cópia da versão selecionada e preenche o campo da URL; clique depois em **Coletar fonte** para recuperar o documento. O cadastro, o título e as notas informadas não são evidências e não habilitam análise sem documentos. A coleta mantém as restrições de URL, rede e formato já existentes.

**Salvar na coleção**, na lista de documentos do dossiê, prepara um cadastro com título, URL, instituição e tema, para conferência e salvamento pelo operador. Se a URL já estiver cadastrada, abre o registro existente sem substituir seus dados automaticamente. Salvar uma referência originada de cópia importada mantém a indicação de que a origem online precisa ser conferida; não muda a origem do documento nem marca a URL como consultada.

Alterar ou arquivar um cadastro não reescreve cópias já selecionadas nos casos nem muda decisões humanas. A cópia identifica referência e versão, consulta local, tema e horário da seleção. Se a fala, a extração ou o plano mudar, o vínculo anterior fica histórico e um destino aberto antes da mudança é rejeitado. Abrir outra sessão ou outro dossiê limpa o destino, preservando a coleção. Referências repetidas da mesma versão e contexto não são duplicadas no caso.

O dossiê e `dossiers[].library_references` no JSON completo incluem somente as referências selecionadas para os casos exportados. O restante da coleção privada não acompanha a sessão. O indicador `current` informa correspondência com o contexto do caso; não garante que a versão seja a mais recente na coleção ou que o conteúdo da URL esteja correto. A análise de evidências continua usando apenas os documentos coletados/importados, sem tratar o cadastro como suporte factual.

A coleção e seu histórico ficam em **library/sources.sqlite3**, separados das capturas e ignorados pelo Git. Outra pasta do aplicativo tem sua própria coleção. Para backup, feche o aplicativo e copie a pasta **library**, além das sessões necessárias. Sessões completas preservam suas referências selecionadas mesmo sem a coleção original. O cadastro não guarda PDFs, HTMLs ou conclusões reutilizáveis. A consulta de decisões anteriores usa os bancos das próprias sessões, conforme descrito a seguir.

### Consultar checagens anteriores

Na aba **Checagens anteriores**, use **Atualizar consulta**. Por padrão, o aplicativo lê as subpastas imediatas de **recordings**; **Escolher pasta** permite apontar outra pasta que contenha sessões. A leitura ocorre em segundo plano, sem API, importação de falas, migração dos bancos ou retomada de tarefas. Nenhum índice permanente é criado. Sessões sem banco de revisão, incompatíveis, corrompidas ou bloqueadas são omitidas com indicação em **Ver avisos**; abra-as separadamente pelo fluxo de recuperação quando necessário.

A lista contém somente casos que ainda guardam uma **decisão humana**, inclusive inconclusiva. Rascunhos e análises de IA não aparecem como checagens concluídas. Por padrão, ficam ocultos os casos cuja fala foi alterada, substituída ou descartada; **Incluir casos históricos / descartados** permite consultá-los com aviso. O estado **Atual na origem** descreve a correspondência entre os registros no instante da consulta; não certifica a validade temporal do dado ou da conclusão. Decisões retiradas do estado atual após uma revisão continuam no histórico da sessão, mas esse histórico integral ainda não faz parte da busca.

Combine palavras em **Buscar**, ignorando acentos e maiúsculas, com o filtro exato de **Tema** e a **Decisão anterior**. A busca exige todas as palavras nos campos do evento, afirmação, contexto, plano ou decisão; não usa correspondência semântica nem lê o texto dos documentos para ranquear resultados. A prévia apresenta citação, versões, contexto, transcrição conferida ou pendente, recortes, justificativa humana e metadados/localizadores das fontes. **Abrir pasta de origem** permite localizar a sessão e seus arquivos; consulte os documentos pelo dossiê de origem. Filtros usam a lista em memória; atualize após alterações nas sessões.

Para registrar uma consulta num caso, abra **Dossiê e fontes → Checagens anteriores**, selecione um antecedente e clique em **Comparar com dossiê atual**. Confira as abas **Contextos de origem e destino** e **Comparação e pendências**. Registre diferenças ou dúvidas sobre afirmação, período e validade, território, indicador/comparação e método/documentos. Escolha **Equivalência a conferir**, **Possível equivalência** ou **Contexto diferente**; nenhum desses estados aprova a reutilização factual. Todos os campos de comparação são obrigatórios, até 2.000 caracteres cada; informação ausente deve permanecer como pendência explícita.

**Registrar antecedente consultado** reconsulta a origem, rejeita alterações desde a lista e confere a versão da fala, extração e plano do destino. Abrir outra sessão ou outro dossiê limpa o destino. O próprio caso não pode ser seu antecedente. Cópias idênticas de sessão aparecem uma vez; cópias com a mesma identidade e conteúdo divergente são omitidas, com aviso para conferência. **Cancelar** durante a consulta e fechar com atividade ou comparação aberta pedem confirmação; cancelar a leitura preserva a lista anterior, inclusive se uma resposta chegar depois.

O novo dossiê recebe uma cópia do antecedente e da comparação, com identidade, versões, impressão digital e horário de consulta. Isso não copia documentos para `sources`, inicia pesquisa, altera uma decisão existente ou aplica o veredito antigo. Colete e confira as evidências pertinentes ao novo caso antes de concluir sua revisão. Alterações posteriores na origem preservam o retrato consultado; mudanças da fala, extração ou plano de destino tornam o registro histórico. Uma nova triagem não herda os antecedentes antigos.

A seção **Checagens anteriores consultadas** e `dossiers[].previous_checks` no JSON incluem somente os antecedentes registrados nos casos exportados. Não incluem caminhos locais, texto extraído de documentos ou outras checagens encontradas na pasta. As fontes do antecedente preservam origem, hashes e localizadores; uma cópia importada continua sem acesso à URL confirmado. O indicador `current` se refere ao contexto do caso de destino, não à atualização online nem ao estado atual da sessão de origem. Copiar a pasta inteira da sessão preserva suas consultas mesmo sem a pasta de origem; o material completo de origem continua necessário para conferir os documentos.

### Encontrar fontes automaticamente

Abra uma afirmação em **Dossiê e fontes** e clique em **Encontrar fontes**. Informe sua **chave Tavily**, confira ou edite a consulta sugerida e clique em **Buscar fontes**. A consulta textual será enviada à Tavily; áudio, documentos e a chave Gemini não são enviados por essa busca. A chave Tavily é independente da chave Gemini, fica somente na memória desta execução e pode ser removida com **Limpar chave**. A triagem pode continuar configurada como local.

Cada clique solicita uma consulta no modo `basic`, com até cinco resultados nos domínios institucionais já permitidos. Não há repetição automática, envio de todos os parágrafos ou busca em segundo plano sem solicitação. O aplicativo pede o consumo em créditos ao provedor e o registra quando informado; não conhece seu saldo, faturamento ou preço contratado. Confira limites e cobranças no seu painel Tavily. A interface e os parâmetros seguem a [documentação oficial da busca](https://docs.tavily.com/documentation/api-reference/endpoint/search).

Os resultados são **URLs candidatas, sem evidência coletada**. O aplicativo normaliza e filtra as URLs recebidas e ignora respostas geradas, snippets e conteúdo bruto. Selecione um resultado e use **Usar URL para coleta**: ele preenche o campo da fonte; clique depois em **Coletar fonte** para recuperar e arquivar o documento. **Descartar candidata** exige justificativa e preserva o registro. Domínio institucional e título de busca não comprovam pertinência ou veracidade.

Consulta, horário, candidatas, descartes e uso informado ficam no SQLite, no dossiê interno e em `dossiers[].discoveries` no JSON completo. Essa descoberta não cria evidências, não habilita análise sem documentos e não altera uma decisão humana existente. Mudanças na fala, na extração ou no plano tornam buscas anteriores históricas; resultados de tarefas iniciadas antes de uma mudança são rejeitados. **Mostrar também buscas de versões anteriores** permite consultá-las, sem usar essas candidatas como atuais. Fontes já coletadas e conclusões continuam com seu próprio controle de versões.

**Cancelar busca** exige confirmação. Fechar a janela com busca ativa também permite cancelar, e o aplicativo mantém a proteção até a tarefa terminar. Uma requisição já enviada pode consumir cota mesmo se cancelada. Sem chave ou acesso ao provedor, **Buscar no navegador**, coleta por URL e importação continuam disponíveis. O transporte Tavily foi exercitado com respostas simuladas; a chamada real depende de uma chave do usuário e ainda precisa de validação operacional.

A busca foi separada da IA porque nosso fluxo guarda candidatas e permite coletar documentos. Os [termos de Grounding with Google Search](https://ai.google.dev/gemini-api/terms#grounding-with-google-search) restringem extrair links para outros usos e identificar páginas para coleta; a integração Gemini existente continua restrita à triagem e à análise dos documentos fornecidos.

### Filtrar a fila de afirmações

Na aba **Afirmações para checagem**, combine **Buscar**, **Escopo**, **Categoria**, **Estado**, **Participante**, **Tema**, **Prioridade** e **Responsável**. O escopo inicial é **Todas**; **Somente atuais** exclui itens substituídos, descartados ou ligados a uma versão antiga da fala. **Históricas / descartadas** permite consultar esses registros sem reativá-los. Os totais distinguem itens exibidos, atuais e históricos. **Ordenar** permite escolher **Mais recentes**, **Prioridade** ou **Ordem da fala**.

A busca ignora maiúsculas e acentos e exige todas as palavras digitadas, inclusive quando estão em campos diferentes da citação, resumo ou contexto. Os seletores combinam os valores cadastrados; **Não identificado** e **Sem tema** localizam campos vazios. O estado considera planejamento, fontes, análise preliminar e decisão humana; itens antigos continuam identificados como desatualizados ou descartados.

Os filtros e a ordenação usam os dados já carregados: não alteram o banco, não iniciam IA ou pesquisa e não mudam o escopo da exportação. Se uma revisão tirar o item do filtro atual, ele sai da lista e a seleção é limpa. Um tema, participante ou responsável selecionado permanece como filtro mesmo sem resultados após uma edição. **Limpar filtros** ou abrir outra sessão restaura a visualização completa e a ordem **Mais recentes**.

### Definir prioridades de revisão

Selecione uma afirmação atual e clique em **Definir prioridade**. Escolha **Alta**, **Normal**, **Baixa** ou **Não definida** e informe uma justificativa de até 2.000 caracteres. A justificativa também é obrigatória para remover a prioridade. Sessões antigas e novas extrações começam sem prioridade atribuída. O nível organiza o trabalho humano; opiniões e promessas não mudam de categoria quando recebem prioridade.

O registro tem revisão e histórico próprios, independentes da fala, da extração e do dossiê factual. Salvar uma prioridade não altera evidências, planejamento, análise preliminar, decisão humana ou tarefas em andamento. A janela sugere considerar relevância pública, urgência e possibilidade de conferir fontes, aplicando os mesmos critérios a todos os participantes; o manual editorial e sua avaliação continuam pendentes.

Se a extração mudar, uma prioridade atribuída fica **A conferir** e deixa de valer na ordenação até confirmação explícita. Reabra **Definir prioridade**, confira nível e justificativa e salve. Uma nova triagem cria outras extrações sem herdar prioridades antigas. Itens substituídos ou descartados preservam o registro como histórico. Alterar somente o plano ou coletar uma fonte não muda a prioridade da extração.

Escolha **Ordenar → Prioridade** para colocar afirmações atuais antes das históricas e organizar as prioridades atuais em Alta, Normal e Baixa. Itens sem prioridade ou a conferir aparecem depois, com desempate pelo intervalo da fala e identificador. **Mais recentes** mantém a ordem de entrada das extrações; **Ordem da fala** usa os tempos da captura. Essa ordenação afeta somente a lista, sem reorganizar tarefas de IA já enfileiradas.

O filtro **Prioridade → A conferir** localiza atribuições que precisam ser revistas. Para ver somente casos atuais de prioridade alta, combine **Somente atuais** e **Alta**. Com escopo **Todas**, prioridades históricas também podem aparecer, identificadas na coluna. Se a prioridade de um item mudar e ele deixar de corresponder ao filtro, a seleção será limpa. Edições concorrentes ou abertas antes de uma mudança da extração são rejeitadas; cancelar uma edição alterada exige confirmação.

Os níveis, justificativas, datas, revisões e indicadores de atualidade acompanham `claims[].priority` e `dossiers[].priority` no JSON, colunas `prioridade_*` no CSV de afirmações e o dossiê interno. O relatório conta prioridades nas extrações atuais de todas as categorias, separando **A conferir**. O denominador das decisões factuais continua restrito às extrações factuais atuais.

### Atribuir responsáveis pelos casos

Selecione uma afirmação atual e clique em **Atribuir responsável**. Digite ou escolha um nome de até 100 caracteres, informe o motivo e use **Salvar atribuição**. As sugestões usam os responsáveis presentes na fila da sessão; esse cadastro é independente dos participantes do debate. Para liberar o caso, use **Limpar nome** e salve com justificativa. Trocas e retiradas preservam nome anterior, motivo, data e versão; salvar os mesmos dados não cria outra revisão.

Essa é uma atribuição local para organizar o trabalho. Ela não autentica a pessoa, envia notificações, restringe quem pode editar ou preenche o responsável pela decisão factual. Esse último continua sendo informado por quem registra a conclusão. Alterar o vínculo não muda prioridade, fala, extração, evidências, planejamento, decisões ou tarefas em execução.

Se a extração mudar, o nome continua visível com **a conferir**. Reabra o editor, confira quem acompanhará a nova versão e salve. Uma nova triagem começa sem responsável; o vínculo anterior permanece no histórico da extração antiga. Alterar somente fontes, plano ou prioridade não exige reconfirmar a atribuição. Editores antigos ou concorrentes são rejeitados, e fechar uma edição alterada exige confirmação.

O filtro **Responsável → Sem responsável** reúne itens sem atribuição e os liberados. Selecionar um nome também encontra seus vínculos a conferir, identificados na coluna; combine com **Somente atuais** para excluir casos históricos. Nomes são comparados exatamente, preservando maiúsculas e acentos. Se um nome coincidir com **Todos** ou **Sem responsável**, o seletor acrescenta **(cadastrado)** à opção da pessoa. Mudar o responsável pode tirar o item do filtro e limpar sua seleção.

O dossiê apresenta o responsável atual e o **histórico completo de atribuições**, com valores anteriores, motivos e versões. JSON inclui `claims[].assignment`, `dossiers[].assignment` e `dossiers[].assignment_history`; o CSV de afirmações inclui `responsavel_caso` e campos `atribuicao_*`, separados de `decisao_humana_responsavel`. O relatório conta vínculos atuais, a conferir e casos sem responsável nas extrações atuais, com distribuição por nome. Contas, permissões, sincronização entre operadores e aceite autenticado de um caso continuam planejados.

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
| event.event_kind | `nao_informado`, `debate_politico`, `propaganda_politica`, `noticiario`, `entrevista` ou `outro`. Registros antigos recebem `nao_informado`. |
| record_id | Identificador estável por registro, composto pela sessão, tipo e identificador local. Permite reconhecer o mesmo registro em outra exportação. |
| record_sha256 | Hash dos campos exportados de um registro; muda quando seu conteúdo ou estado muda. |
| content_sha256 / exported_at | Hash do retrato e horário UTC de sua cópia. O horário é excluído do hash; reexportar dados iguais na mesma versão mantém o hash. |
| paragraphs / origin_paragraphs | Falas do escopo escolhido e componentes adicionais de origem. Seus identificadores locais se relacionam dentro de `session_id`. |
| claims.source_current | A afirmação corresponde à versão atual e não foi descartada. Esse campo não classifica sua veracidade. |
| claims.claim_revision / automatic_extraction / extraction_review | Versão da extração, conteúdo automático preservado após edição e origem, data e justificativa da revisão do operador. A revisão da fala continua em `revision`; nenhuma dessas revisões equivale a decisão factual. |
| claims.priority / dossiers.priority | Nível e justificativa manuais, revisão própria, data e revisões da fala e extração usadas. `current` distingue a atribuição atual; `needs_review` exige reconferir uma prioridade após mudança da extração. Sem atribuição, `level` é `unset` e `revision` é 0. |
| claims.assignment / dossiers.assignment / dossiers.assignment_history | Nome local do responsável pelo caso, motivo, revisão e contexto da atribuição, separados de `decision.reviewer`. `current` indica correspondência com a extração, inclusive de uma retirada; `needs_review` pede reconferir um vínculo atribuído. O histórico guarda valores anterior e novo, sem reativá-los. |
| dossiers.library_references | Cópia dos metadados e da versão da referência selecionada na coleção, com consulta, tema, horário e atualidade do contexto. São candidatas de pesquisa, separadas de `sources`; não inclui a coleção inteira. |
| dossiers.previous_checks | Antecedentes explicitamente consultados, versões e impressão digital da origem, decisão humana anterior e comparação de contextos. Referências de pesquisa, separadas da decisão e dos documentos do caso atual; não inclui os demais resultados ou caminhos locais. |
| claims.topic_annotation | Termo informado, correspondência textual, origem IA/operador, versão do vocabulário e cópia apenas da definição usada. Ausente em registros anteriores; separado da decisão factual. |
| paragraphs.speaker_assignment / claims.speaker_assignment | Associação humana assistida por vozes: análise, grupo, participante, motivo, horário, revisão da fala, hashes e motor. `current` distingue atribuição atual de histórica; não significa transcrição ou fato conferido. Ausente quando não há associação assistida. |
| dossiers | Análise preliminar e decisão humana em campos separados, com revisão e indicadores de atualidade. |
| dossiers.plan | Pergunta, recortes, lacunas, URLs candidatas, origem e data do plano. Rascunho de IA não corresponde a conferência humana ou evidência coletada. |
| sources | Fontes associadas às afirmações incluídas, com cópia textual e localizadores. `url_access_confirmed` distingue consulta à URL de importação local ou origem não informada. |

Cada CSV repete **evento_id**, **sessao_id**, **registro_id**, **registro_sha256**, **snapshot_sha256** e o horário de exportação. A coluna **origem_atual** das afirmações indica correspondência com a versão da fala; **preliminar_atual** e **decisao_atual** informam se as conclusões exibidas ainda se aplicam. Registros históricos ficam identificados como **historical** no estado do dossiê.

Na versão 0.23, **evento_tipo** identifica o conteúdo em todos os CSVs. Falas e afirmações acrescentam **falante_analise_id**, **falante_voz_id**, **falante_atribuido_em**, **falante_motivo** e **falante_atribuicao_atual**. O identificador de voz começa em zero no JSON/CSV; a interface soma um para exibir **Voz 1**. Ele só tem significado junto da análise correspondente. Consumidores devem localizar colunas pelo cabeçalho; os novos campos são aditivos ao contrato de versão 1.

Cada exportação copia os dados naquele instante. CSVs produzidos em momentos diferentes podem ter hashes de retrato diferentes durante uma captura ou revisão. O JSON reúne as tabelas do mesmo retrato. As definições de campos e a escrita dos arquivos estão em [factcheck/exports.py](factcheck/exports.py). As identidades de sessões antigas são preenchidas na abertura, sem reanalisar as falas; copiar a pasta completa com o SQLite preserva essas identidades.

### Relatório do ensaio

Encerre a captura, abra **Exportar sessão** e escolha **Relatório do ensaio · TXT** para leitura ou **Relatório do ensaio · JSON** para processar as métricas. A tarefa usa a mesma confirmação de cancelamento e proteção de fechamento das demais exportações. O seletor de itens históricos fica desabilitado: o relatório separa as contagens atuais das tentativas históricas automaticamente.

O resumo apresenta parágrafos ativos, conferência humana, participante indefinido, triagem concluída, categorias, extrações revisadas e pendências de fontes, planejamento, análise preliminar e decisão humana. A proporção de decisões humanas usa como denominador **somente as extrações atuais classificadas como factuais, incluindo reclassificações do operador**. Ela não representa precisão nem cobertura das afirmações presentes no vídeo. Combinações, descartes e correções não contam as versões antigas como afirmações atuais. Os campos do relatório `detected_factual` e `human_decisions_on_detected_factual` acompanham essa classificação atual.

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

O banco **review.sqlite3** guarda o cadastro atual, originais, revisões humanas, análises, afirmações, buscas de candidatas, cópias extraídas das fontes e dossiês com histórico. Os arquivos de transcrição e parágrafos preservam o reconhecimento original; o texto corrigido aparece na aba de revisão e no banco. A identificação automática de quem fala e a pesquisa contínua ainda estão pendentes; a descoberta de links pode ser solicitada por **Encontrar fontes**.

### Revisar as afirmações extraídas

Na aba **Afirmações para checagem**, selecione um item e clique em **Revisar afirmação**. É possível alterar a citação, o resumo, a categoria e o tema, registrando uma justificativa. Por exemplo, uma opinião extraída como factual pode voltar à categoria **Opinião**, saindo da fila factual. Essa revisão não confere a transcrição nem registra um veredito.

A citação deve ser um intervalo literal do texto atual da fala, incluindo negações e qualificadores. O editor rejeita citações inventadas, mudanças silenciosas no recorte e resumos que omitam negação explícita ou acrescentem números ausentes. Citações idênticas a outro item atual do mesmo parágrafo também são rejeitadas. Para corrigir palavras do reconhecimento, use **Revisar origem** e depois gere a triagem da nova versão. Os recortes de pesquisa continuam no planejamento do dossiê.

Salvar incrementa **claim_revision**, preserva a identidade da afirmação e a extração automática original e registra a mudança no histórico. A fala e suas marcações de tempo mantêm sua revisão própria. Análise e decisão dependentes são invalidadas; fontes são preservadas e o plano fica marcado como **Planejamento a conferir**. Pesquisas e triagens iniciadas antes da edição não podem substituir o conteúdo revisado. Uma nova triagem solicitada depois da edição pode criar outras extrações, mantendo as anteriores como históricas.

O detalhe mostra a categoria atual, a revisão do operador e a extração automática preservada. O JSON inclui essa origem e a revisão atual; o CSV acrescenta campos de revisão, categoria e citação automáticas e justificativa. As revisões intermediárias completas permanecem no histórico do SQLite. Sessões anteriores sem **claim_revision** são lidas como revisão **1**, sem reprocessamento. Salvar os mesmos dados de uma extração já revisada não invalida uma decisão posterior. Cancelar um editor alterado exige confirmação.

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

**requirements.lock** fornece o backend CPU para Windows x64. Para um ambiente novo com GPU NVIDIA e driver compatível, use **requirements-gpu.lock** no comando de instalação. Essa configuração inclui o wheel CUDA e as bibliotecas NVIDIA na `.venv`; não instala drivers nem altera o toolkit global ou o PATH do Windows. A triagem usa o backend CUDA 13 e a opção Whisper NVIDIA da 0.24 usa os runtimes CUDA 12 e cuDNN 9 fixados no arquivo. O contínuo permanece em CPU. Whisper NVIDIA foi exercitado nesta RTX 5060 Laptop com driver 621.01; confira [preparação, métricas e limites](docs/desempenho-transcricao.md). Ao trocar um backend já instalado, recrie o ambiente ou reinstale explicitamente o wheel correspondente.

O leitor PyAV está limitado a uma versão compatível com o faster-whisper utilizado. Implementações de referência: [PyAudioWPatch](https://github.com/s0d3s/PyAudioWPatch), [sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx) e [faster-whisper](https://github.com/SYSTRAN/faster-whisper). Referência das bibliotecas NVIDIA: [instalação de runtimes por pip no Windows](https://docs.nvidia.com/cuda/cuda-installation-guide-microsoft-windows/).

## Diagnóstico e testes

```powershell
.\.venv\Scripts\python.exe -m factcheck --list-devices
.\.venv\Scripts\python.exe -m factcheck --record-seconds 20
.\.venv\Scripts\python.exe -m factcheck --record-seconds 5 --no-transcription
.\.venv\Scripts\python.exe -m factcheck --engine whisper --prepare-model
.\.venv\Scripts\python.exe -m factcheck --engine whisper --record-seconds 20
.\.venv\Scripts\python.exe -m scripts.compare_transcription recordings\PASTA_DA_SESSAO\audio.wav --profiles streaming-cpu whisper-cpu whisper-cuda
.\.venv\Scripts\python.exe -m scripts.rehearse_recovery
.\.venv\Scripts\python.exe -m factcheck --replay-wav recordings\PASTA_DA_SESSAO\audio.wav
.\.venv\Scripts\python.exe -m factcheck --prepare-speaker-models
.\.venv\Scripts\python.exe -m scripts.validate_project
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Para escolher uma saída pela linha de comando, acrescente **--device** com o índice informado pela listagem. **--engine streaming** é o padrão; **--model tiny|base|small** se aplica ao modo Whisper. **--paragraph-pause 1.5** configura a pausa sugerida entre parágrafos. Os testes verificam preservação de amostras, formato WAV, medição de nível, horários, união das janelas, substituição das prévias, organização em parágrafos, encerramento, falhas e cancelamento. As gravações, modelos, caches e logs são ignorados pelo Git.

**paragraphs.jsonl** é um histórico de atualizações: para obter o estado atual, selecionar a maior **version** de cada **paragraph_id** dentro da sessão. O campo **closed** indica que o agrupamento foi encerrado, e **end_reason** distingue conclusão, cancelamento e interrupção; isso não equivale a validação editorial.

### Validação realizada neste computador

- Na versão 0.25, **586 testes passaram em 218.242 s** localmente. A suíte cobre inclusão/divisão, citações/cálculos, fila e limites, pausas, avaliação humana, backup/restauração, falhas de armazenamento e proteção de fechamento. Sintaxe, documentação, SVGs e pacote também foram verificados; consulte a [validação da entrega](docs/entrega-mvp-local.md#validação-do-fechamento-025). Não houve chamada real de API ou decisão sobre caso político real neste fechamento.
- Na versão 0.24, os **529 testes automatizados passaram**, em 178,992 s, incluindo os controles de captura e fechamento, cadastro e persistência, edição com histórico, reprodução do intervalo correto de áudio, restauração de citações, validação de números e negações e invalidação de resultados durante uma correção concorrente.
- Na versão 0.24, os testes cobrem opção NVIDIA explícita, aquecimento sintético consumido antes de gravar, falha de runtime sem troca silenciosa para CPU, limpeza dos diretórios de DLL, seleção pela interface, relatório antigo sem medidas inventadas, métricas de inferência separadas do pipeline, PCM exato, modelos/áudio alterados, preservação de JSON existente e comparação interrompida com resultados já salvos. Os [ensaios nativos](docs/desempenho-transcricao.md) usaram os três perfis com o mesmo WAV curto e NVIDIA com uma gravação de 336,341 s. Não foram chamadas APIs ou criadas decisões factuais. A nova seleção e os diagramas foram conferidos visualmente; a avaliação de fidelidade e a carga simultânea com Qwen continuam pendentes.
- A [execução Windows da 0.24 no GitHub](https://github.com/elcelsius/Fact-Check-AI/actions/runs/40150757194), sobre o código `ddd71a6`, aprovou os testes, a documentação, os SVGs reproduzíveis e o pacote. O backend CPU funciona sem os runtimes NVIDIA opcionais; o pacote inclui os novos módulos e o auxiliar local de download.
- Na versão 0.23, os testes cobrem entrada WAV no ritmo original, PCM exato, cancelamento, arquivo alterado ou incompleto, ausência de dispositivo, vozes anônimas, trechos mistos, associação humana transacional, revisões antigas, recuperação e proveniência exportada. Incluem tipo de conteúdo em sessões antigas/novas e cuidado com fala reportada. Foram conferidos o pacote Python, seus recursos, os links locais e os SVGs renderizados. Os [ensaios nativos e seus limites](docs/entrega-mvp-local.md#validação-desta-entrega) distinguem execução técnica de precisão editorial. O [workflow Windows](.github/workflows/tests.yml) executa a suíte, validação e construção do pacote. A [primeira execução no GitHub](https://github.com/elcelsius/Fact-Check-AI/actions/runs/40135380140), sobre o código `105aded`, passou em Windows 2022/Python 3.12: 510 testes em 318,217 s, documentação, SVGs reproduzíveis e pacote com seus recursos.
- Na versão 0.22, os testes exercitam cadastro, duplicação de nomes/variações, edição concorrente, arquivamento, restauração, rollback, leitura sem escrita, normalização textual, termos desconhecidos e versão capturada por tarefa. Cobrem histórico automático e humano, preservação dos casos após mudanças do cadastro, exportação somente do tema usado, sugestões no editor e rejeição de vocabulário alterado durante a revisão. Aba e cadastro foram conferidos em dois tamanhos cada, assim como a revisão da afirmação. Os SVGs foram atualizados e renderizados. O ensaio foi fictício e não chamou APIs ou alterou casos políticos reais; a adequação editorial dos temas continua pendente.
- Na versão 0.21, os testes exercitam consulta somente de leitura, filtros locais, casos históricos, bancos ausentes/antigos/corrompidos/bloqueados, deduplicação e conflito entre cópias, cancelamento, fechamento, origem e destino alterados durante a comparação, campos obrigatórios e não transferência de conclusões. Cobrem preservação dos arquivos originais, procedência importada, decisões e tarefas do destino, retratos consultados e exportação apenas dos antecedentes registrados. A aba foi conferida em 1120 × 860 e 1000 × 760; as duas abas da comparação, em 920 × 780 e 840 × 700. Os SVGs foram atualizados e renderizados. O ensaio usou dados fictícios, sem API ou alterações nos casos políticos reais; equivalência factual e validade temporal continuam sob conferência humana.
- Na versão 0.20, os testes exercitam cadastro, edição, arquivamento, restauração, busca local, URLs duplicadas, versões concorrentes e rollback da coleção. Cobrem reutilização entre sessões, cópias imutáveis das seleções, destinos desatualizados, ausência de coleta automática, preservação da origem de cópias importadas e exportação apenas das referências usadas. A coleção foi conferida em 1120 × 860 e 1000 × 760; as duas abas do editor, em 900 × 760 e 820 × 700. O ensaio fictício selecionou uma referência, preservou a decisão humana após alteração posterior do cadastro e manteve outra referência privada fora da exportação. Os SVGs foram atualizados e renderizados. Nenhuma API foi chamada ou referência selecionada para os casos políticos reais.
- Na versão 0.19, os testes exercitam atribuição, troca e retirada de responsável com motivo, revisão própria, histórico consultável no dossiê e JSON, concorrência e conferência após mudança da extração. Cobrem a separação entre responsável pelo caso e revisor factual, preservação de prioridade e tarefas, nomes coincidentes com marcadores de filtro, exportações, relatórios e bancos anteriores. A fila foi conferida em 1120 × 860 e 1000 × 760; o editor, em 760 × 540 e 700 × 500. O ensaio fictício redistribuiu e liberou um caso, preservou o revisor de uma decisão e manteve pendente uma prioridade que exigia conferência. Os SVGs foram atualizados e renderizados. Nenhuma API foi chamada ou atribuição feita aos casos políticos reais.
- Na versão 0.18, os testes exercitam prioridade com revisão própria, justificativa, histórico, concorrência, remoção, conferência após mudança da extração, não transferência entre triagens e preservação de decisões e tarefas. Cobrem filtros e ordenação sem novas consultas ao banco, JSON/CSV, hashes, relatórios e bancos anteriores sem a tabela de prioridades. A fila foi conferida em 1120 × 860 e 1000 × 760; o editor, em 760 × 540 e 700 × 500. O ensaio fictício reconfirmou uma prioridade pendente, limpou a seleção ao sair do filtro e preservou a decisão humana. Os diagramas foram atualizados e renderizados. Nenhuma API foi chamada e os casos políticos reais permaneceram sem novas decisões.
- Na versão 0.17, os testes exercitam busca Tavily com transporte simulado, validação de URLs, duplicação, cotas, erros seguros, chave em memória, cancelamento tardio, mudanças de fala/extração/plano, descarte justificado, exportação e preservação de decisões. A janela foi inspecionada em 1000 × 740 e 900 × 650. O ensaio fictício recebeu duas candidatas, omitiu uma URL fora da coleção e selecionou um link sem coletá-lo automaticamente. Os SVGs foram atualizados e renderizados. A chamada real com chave Tavily continua pendente; não houve envio de falas ou alteração dos casos reais.
- Na versão 0.16, os testes exercitam filtros combináveis por texto e contexto, escopo atual/histórico, ausência de metadados, preservação de seleção válida e limpeza ao ocultar um item. A busca local não consulta novamente o banco nem inicia IA ou pesquisa. A interface foi conferida em 1120 × 860 e 1000 × 760, com rodapé e controles visíveis.
- Na versão 0.15, os testes exercitam reclassificação e edição da extração com identidade e revisão próprias, preservação do original automático, atualização da fila, histórico intermediário, rejeição de duplicação e de editores antigos, proteção de negações e invalidação de pesquisas e triagens iniciadas antes da revisão. Também cobrem preservação das fontes, plano a conferir, exportações e relatórios, leitura de registros antigos e cancelamento do editor. A interface foi inspecionada com uma opinião fictícia inicialmente marcada como factual. Não houve nova inferência nem alteração dos rascunhos reais do ensaio; a conferência desses casos permanece pendente.
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

O foco inicial continua sendo checagem política em uso interno. A primeira versão aceita também propaganda política e noticiários, conforme a decisão de escopo de 24/10/2026. O piloto com material representativo e referência humana será feito antes de assumir desempenho ou qualidade para eventos ao vivo.

O projeto avaliará a redução de trabalho humano junto com a qualidade das evidências, a cobertura das afirmações, o tempo até a revisão e o custo. As escolhas técnicas locais estão consolidadas na entrega. Orçamento, equipe editorial, evento e metas operacionais serão definidos na preparação do piloto.

## Validação após a entrega local

Ouvir a saída de **Whisper NVIDIA** e comparar com os motores CPU usando uma referência humana. O ganho medido não elimina os picos de atraso; testar depois a operação com triagem simultânea e manter os resultados de qualidade separados dos tempos. O [guia de desempenho](docs/desempenho-transcricao.md) inclui comandos, medidas e roteiro para completar uma checagem humana.

Usar **Testar conexão** para validar uma chave Gemini e **Encontrar fontes** para exercitar uma chave Tavily no Windows, registrando disponibilidade e consumo real. A coleta real foi exercitada em uma página do MJSP; ampliar a validação para outros domínios e diagnosticar a tentativa do TSE antes de generalizar disponibilidade. Cópias importadas continuam com origem pendente de conferência. Avaliar transcrição, triagem e dossiês com gravações representativas e anotações humanas. Pesquisa contínua e outros provedores de busca dependem de novos limites e ensaios. A definição editorial do piloto e seu conjunto de referência continuam no checklist.

O [checklist amplo](docs/checklist-desenvolvimento.md) preserva o histórico e as tarefas de avaliação e evolução. A [entrega do MVP local](docs/entrega-mvp-local.md) registra o escopo aceito e o roteiro completo de uso; a [metodologia editorial proposta](docs/metodologia-editorial.md) orienta o próximo ensaio humano. O material pode ser debate, propaganda política, noticiário ou entrevista. Em relatos e reexibições, confira a data original e diferencie a voz de quem apresenta da pessoa cuja declaração foi citada. Pesquisa contínua, acervos externos, correspondência semântica e operação em equipe ficam para versões posteriores.
