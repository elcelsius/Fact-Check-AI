# Operação e recuperação de uma sessão

Procedimento do MVP local Windows, versão **0.23.0**, de 24/10/2026. A recuperação é local; nenhuma pesquisa ou chamada à IA é retomada automaticamente ao abrir uma sessão. Consulte também o [fluxo interno](diagramas/fluxo-interno.svg) e a [jornada do usuário](diagramas/fluxo-usuario.svg), com as funções planejadas em caixas tracejadas.

A [entrega do MVP local](entrega-mvp-local.md) detalha o escopo escolhido, o botão **Ensaiar WAV salvo**, a aba **Falantes** e os resultados da versão 0.23. Em **Dados da transmissão**, selecione debate, propaganda política, noticiário, entrevista ou outro conteúdo; confira a data original e a autoria de declarações relatadas.

## Preparar e manter a coleção de referências

1. Abra **Coleção de fontes**, antes ou depois de uma captura. O catálogo é local e compartilhado entre as sessões da mesma pasta do aplicativo; não exige chave de API.
2. Use **Nova referência** para registrar título, URL HTTPS institucional, instituição informada e de um a oito temas separados por ponto e vírgula. Nas abas **Cadastro** e **Metodologia e limites**, informe periodicidade, método, recortes, limitações e observações quando conhecidos. Registre o motivo do cadastro e salve. Campos metodológicos ausentes ficam a definir; não preencha por suposição.
3. Combine **Buscar**, **Tema** e **Incluir arquivadas**. A busca exige todas as palavras, ignora acentos e maiúsculas e consulta os campos do cadastro. O tema é comparado exatamente. **Atualizar lista** recarrega alterações de outra janela; filtros não iniciam coleta ou chamadas externas.
4. Para corrigir o cadastro, selecione **Editar referência** e justifique. Para retirar da lista ativa, use **Arquivar referência**; para voltar, inclua arquivadas e use **Restaurar referência**, também com motivo. Editar uma arquivada não a restaura. O histórico completo do cadastro aparece abaixo da lista. Uma URL já registrada deve ser editada ou restaurada, sem criar duplicatas.
5. Para selecionar no caso, abra uma afirmação atual em **Dossiê e fontes** e use **Coleção de fontes**. Confira o destino exibido e use **Usar URL no dossiê**. Essa ação guarda uma cópia da versão do cadastro e preenche a URL; use **Coletar fonte** para efetivamente obter e conferir o documento. Sem destino explícito, ou com a referência arquivada, essa ação fica indisponível.
6. Se já há documento no dossiê, **Salvar na coleção** prepara seu cadastro para revisão. O operador ainda precisa conferir campos e motivo. A origem de uma cópia importada continua sem acesso online confirmado; criar referência não modifica essa condição.

Um cadastro alterado enquanto o editor está aberto é rejeitado ao salvar; uma versão antiga da lista não pode ser selecionada como atual. Alterações da fala, extração ou plano também rejeitam um destino antigo. Trocar de sessão ou abrir outra afirmação limpa o destino. O filtro de tema permanece ativo se uma edição retirar seu último resultado; limpar filtros restaura a lista padrão.

Referências selecionadas ficam na seção **Referências da coleção · candidatas, não evidências** do dossiê e em `dossiers[].library_references` no JSON. Elas não habilitam análise factual sem documentos, alteram decisões ou são enviadas à análise como evidências. Metadados de acesso/publicação continuam pertencendo às fontes efetivamente coletadas. O retrato guardado no caso permanece igual se a coleção mudar depois; `current` indica contexto do caso, sem afirmar atualidade online ou correspondência com o cadastro mais recente. Consultas locais ficam registradas na seleção; buscas sem seleção são somente filtros de visualização.

A coleção fica em **library/sources.sqlite3**, com histórico próprio, fora do Git e separada de `recordings`. Para backup ou transferência, feche o aplicativo e copie a pasta **library**. As sessões guardam suas próprias seleções e podem ser lidas sem a coleção original. Exportar uma sessão inclui apenas referências selecionadas nos casos do escopo; não copia toda a coleção privada. O primeiro incremento não arquiva binários nessa biblioteca nem reutiliza conclusões de checagens. A preparação e a avaliação editorial dos materiais continuam pendentes.

## Consultar e comparar checagens anteriores

1. Abra **Checagens anteriores → Atualizar consulta**. A pasta padrão é `recordings`; para consultar outra coleção de sessões, use **Escolher pasta**. Somente suas subpastas imediatas são lidas. A consulta ocorre em segundo plano, não exige API, não escreve nas sessões e não substitui o procedimento de recuperação. Bancos ausentes, antigos, bloqueados ou ilegíveis geram avisos consultáveis em **Ver avisos**, sem impedir outros resultados.
2. Combine **Buscar**, **Tema** e **Decisão anterior**. Todas as palavras precisam ocorrer nos metadados/contexto; a busca ignora acentos e maiúsculas e não é semântica. A lista contém apenas decisões humanas ainda presentes no estado salvo dos casos. Conclusões removidas após correções permanecem no histórico da sessão, fora desse primeiro mecanismo de busca.
3. Confira citação, contexto, transcrição conferida ou pendente, recortes, revisor e data da decisão e fontes/localizadores na prévia. **Atual na origem** significa apenas que a fala/extração ainda corresponde aos registros consultados. Marque **Incluir casos históricos / descartados** somente para examinar decisões de versões substituídas, claramente identificadas. **Abrir pasta de origem** localiza os arquivos; abra a sessão separadamente para conferir as cópias completas dos documentos.
4. Para associar a pesquisa, abra o caso de destino em **Dossiê e fontes → Checagens anteriores** e use **Comparar com dossiê atual**. Confira os contextos e registre diferenças ou pendências nos cinco campos: afirmação/contexto, período/validade, território, indicador/comparação e método/documentos. Não presuma equivalência diante de campos ausentes. O estado **Possível equivalência** é uma anotação de pesquisa, sem aprovação factual.
5. Use **Registrar antecedente consultado**. A origem é reconsultada antes de salvar; uma decisão, fala, extração, plano ou conjunto de fontes alterado exige atualizar a lista. O destino também é conferido. O próprio caso não pode ser seu antecedente. Consultas idênticas não duplicam o registro; novas notas preservam ambas as versões. Trocar de sessão ou dossiê limpa o destino.
6. Confira a seção **Checagens anteriores consultadas**. A cópia preserva identidade, versões, impressão digital, fontes/metadados, decisão anterior e comparação. Alterações posteriores na origem não reescrevem esse retrato. Mudanças da fala/extração/plano de destino tornam o vínculo histórico. Colete e examine documentos no caso atual para fundamentar sua própria decisão; a consulta não acrescenta evidências, altera tarefas ou transfere vereditos.

Cópias idênticas da mesma sessão são deduplicadas na lista. Quando cópias da mesma identidade e caso têm conteúdo divergente, o caso é omitido com aviso; confira as cópias antes de consultar. A varredura não pesquisa subpastas profundas, arquivos JSON exportados ou acervos externos. Filtros não releem os bancos; atualize após alterações. Cancelar pede confirmação e preserva a lista anterior, mesmo que a resposta termine depois do pedido.

O JSON exporta apenas `dossiers[].previous_checks` dos casos selecionados, sem caminhos locais, texto dos documentos ou o restante do acervo. Os documentos do antecedente continuam separados de `sources`; importados não passam a ter acesso online confirmado. `current` descreve o contexto do destino, não uma reconferência da origem ou de sua validade online. As sessões guardam suas próprias cópias consultadas, mas o exame completo das evidências requer preservar a pasta da sessão anterior.

## Preparar e manter o vocabulário de temas

1. Abra **Temas → Novo tema**. Informe nome, até doze variações separadas por ponto e vírgula, descrição opcional e motivo. Nomes/variações têm até 100 caracteres, descrição até 1.500 e motivo até 2.000. O aplicativo começa sem temas editoriais predefinidos; cadastre os agrupamentos apropriados ao ensaio.
2. Use **Buscar**, **Editar tema**, **Arquivar tema** e **Restaurar tema** para manter o cadastro. Busca local ignora caixa e acentos. Nomes e variações pertencem a um único cadastro, inclusive arquivados; edite explicitamente um termo para liberá-lo. Arquivar retira das próximas correspondências e editar não restaura. O histórico permite conferir versões e motivos.
3. Cada entrada na fila de triagem captura o vocabulário ativo. A resposta da IA passa por normalização textual completa de nome/variação; texto, contexto, categoria e conclusão não são inferidos pelo vocabulário. Termo desconhecido permanece livre e identificado. Descrições e lista de temas não são enviadas à API; a requisição da triagem continua apenas com seu conteúdo habitual.
4. Confira **Organização por tema** no detalhe da afirmação ou no dossiê. São mostrados termo original, origem IA/operador, definição usada e versões. Alterar o cadastro vale para as próximas entradas, preservando tarefas enfileiradas e casos existentes. Uma nova triagem deve ser solicitada explicitamente para aplicar outros temas a trechos já analisados.
5. Na revisão da afirmação, escolha um nome sugerido ou escreva texto livre e justifique. Um vocabulário alterado durante a edição exige reabrir o editor. Salvar segue os controles existentes de revisão da extração, preserva o automático e invalida conclusões dependentes quando aplicável. Cadastrar ou arquivar temas, isoladamente, não altera decisões, prioridades, responsáveis ou fontes.

O cadastro e seu histórico ficam em `library/topics.sqlite3`, fora do Git e compartilhados entre sessões da mesma pasta do aplicativo. Feche o aplicativo antes de copiar `library` para backup ou transferência. A ausência do arquivo permite temas livres; arquivo presente mas inválido/indisponível bloqueia novas entradas na triagem até conferência, sem interromper a captura. Preserve uma cópia e investigue o cadastro; a triagem não tenta repará-lo ou apagá-lo automaticamente.

JSON e dossiê guardam apenas a definição temática usada, além de identidade/revisão/impressão digital do vocabulário e termo original. O CSV acrescenta esses identificadores, estado e origem. Os demais temas privados não acompanham a exportação. Sessões antigas e termos da coleção de fontes/antecedentes mantêm seus valores até revisão explícita; não há renomeação em lote ou migração automática dos temas.

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

## Localizar afirmações e pendências

Em **Afirmações para checagem**, use os filtros acima da lista. Por exemplo, escolha **Somente atuais**, categoria **Factual** e estado **Planejamento a conferir** para localizar planos que precisam de revisão. Combine participante e tema quando necessário. **Não identificado** e **Sem tema** procuram campos sem valor; **Todos** remove aquela restrição.

**Buscar** exige todas as palavras digitadas, ignora maiúsculas e acentos e consulta citação, resumo, contexto e campos extraídos. Os seletores usam valores exatos, para não unir participantes ou temas distintos. O estado exibido prioriza descarte e desatualização; uma decisão antiga não aparece como revisão humana atual. O contador de atuais e históricos considera a sessão inteira, enquanto **Exibindo** conta os resultados visíveis.

Os filtros só mudam a visualização, sem ler novamente o banco, enviar falas ou iniciar análises. A exportação mantém seu próprio escopo. Se uma revisão mudar a categoria, o tema ou outro campo usado no filtro, a linha pode sair da lista e sua seleção é limpa. Um filtro selecionado continua ativo mesmo se perder o último resultado. Use **Limpar filtros** para voltar a todos os itens; abrir outra sessão também limpa os filtros. A aba **Dossiê e fontes** mantém seu próprio seletor.

## Priorizar a revisão

Em **Afirmações para checagem**, selecione um item atual e use **Definir prioridade**. Escolha Alta, Normal, Baixa ou Não definida e registre a justificativa, inclusive ao remover o nível. O editor sugere critérios gerais; a definição editorial precisa ser aplicada de forma consistente entre participantes e temas. Essa ação não confere a fala, não reclassifica a extração e não decide a veracidade.

Para concentrar a revisão, combine **Escopo → Somente atuais**, **Prioridade → Alta** e **Ordenar → Prioridade**. A ordenação coloca atuais antes de históricos, prioriza Alta, Normal e Baixa e deixa sem prioridade e a conferir depois. O desempate usa intervalo da fala e identificador. Mais recentes significa a ordem de entrada das extrações; a alteração da prioridade não muda essa data. Limpar filtros ou abrir outra sessão restaura a lista completa e a ordem Mais recentes.

Uma extração alterada deixa a prioridade atribuída **A conferir**. O nível anterior permanece no histórico e não promove o item na ordenação. Reabra o editor, confira justificativa e nível e salve para confirmar a extração atual. Uma nova triagem não transfere o nível para outras extrações; descarte e substituição preservam a prioridade histórica. Os filtros de nível também encontram esses registros quando o escopo inclui históricos, com identificação explícita.

O registro usa revisão própria e rejeita editores concorrentes ou anteriores a uma mudança da extração. Fontes, plano, análise preliminar, decisão humana e trabalhos já iniciados permanecem independentes. Editar somente plano ou fontes não altera a prioridade. A mudança não dispara chamadas externas nem reorganiza a fila de execução dos motores. Fechar ou cancelar um editor alterado pede confirmação; salvar pode fazer o item desaparecer do filtro ativo, limpando a seleção.

O SQLite mantém níveis e justificativas anteriores. JSON e dossiê incluem a atribuição e seu estado; o CSV de afirmações acrescenta `prioridade`, `prioridade_revisao`, `prioridade_atual`, `prioridade_precisa_conferencia`, `prioridade_justificativa` e `prioridade_em`. O relatório resume os níveis das extrações atuais de todas as categorias e mantém o denominador factual separado. Sem prioridade antiga registrada, os campos começam em `unset`, revisão 0, sem uma data inventada.

## Atribuir e redistribuir casos

1. Em **Afirmações para checagem**, escolha um item atual e use **Atribuir responsável**. Digite ou selecione um nome da sessão, com até 100 caracteres, e informe o motivo. Esse nome não identifica o participante que falou.
2. Use **Salvar atribuição**. Para trocar a pessoa, altere o nome e explique a redistribuição. Para liberar, use **Limpar nome** e justifique a retirada. As versões anteriores continuam disponíveis no dossiê e no JSON completo.
3. Combine **Responsável** com **Somente atuais** para acompanhar os casos de uma pessoa. **Sem responsável** também inclui casos liberados. O nome selecionado permanece como filtro após perder seu último resultado, evitando ampliar a lista silenciosamente; limpar filtros ou abrir outra sessão restaura Todos.
4. Se aparecer **a conferir**, a extração mudou. Confira o vínculo e salve para associá-lo à nova versão. O filtro pelo nome continua encontrando essa pendência. Uma nova triagem não transfere a atribuição para outra extração; casos antigos são identificados como históricos.
5. Confira as mudanças em **Dossiê e fontes**, na seção **Responsável pelo caso**. O histórico lista nome anterior e novo, motivo, horário e versões da extração e da fala usados. Abrir esse histórico não reativa uma atribuição antiga.

A atribuição é um registro local por nome. Ela não autentica pessoas, restringe edição, envia notificações nem substitui o responsável que assina uma decisão factual. Revisões concorrentes do vínculo ou abertas antes de uma alteração da extração são rejeitadas. Cancelar ou fechar um editor alterado pede confirmação. Mudanças de responsável não invalidam prioridade, fontes, plano, análise ou decisão; alterar só esses campos também não muda o vínculo.

O JSON guarda a atribuição atual e `dossiers[].assignment_history`. O CSV distingue `responsavel_caso` e `atribuicao_*` de `decisao_humana_responsavel`. O relatório apresenta atribuições atuais, a conferir, sem responsável e contagens por nome nas extrações atuais de todas as categorias. Esses números não medem a produtividade ou a identidade de uma pessoa. Contas, permissões, aceite autenticado e operação simultânea em máquinas distintas continuam pendentes.

## Revisar a extração de uma afirmação

Em **Afirmações para checagem**, use **Revisar afirmação**. Confira a citação no texto atual da fala, ajuste resumo, categoria e tema e registre o motivo. Uma frase de opinião classificada incorretamente pode ser reclassificada, sem transformar essa revisão em aprovação factual. Se houver erro no texto transcrito, use **Revisar origem** e gere a triagem da revisão atual antes de editar a nova extração.

A citação salva deve ser literal e preservar negações e qualificadores. O editor rejeita alterações de texto que precisariam ser corrigidas na origem, resumos com número ausente ou negação omitida e duplicação de citação entre itens atuais do mesmo parágrafo. Esses controles limitam erros específicos; não asseguram fidelidade semântica ou veracidade.

O identificador da afirmação permanece e `claim_revision` aumenta, independentemente da revisão do parágrafo. O primeiro conteúdo automático fica em `automatic_extraction`; `extraction_review` identifica a origem do operador, a data e a justificativa. A comparação aparece no detalhe e nas exportações. As revisões intermediárias completas ficam no histórico do SQLite. Registros antigos sem a nova versão são tratados como revisão 1.

Uma mudança invalida a análise e a decisão atuais e rejeita resultados de triagem ou pesquisa iniciados antes dela. Fontes permanecem arquivadas, e o planejamento fica com `needs_review: true` e a revisão da extração que usou. A fila mostra **Planejamento a conferir**. Abra **Planejar checagem**, confira a pergunta e os recortes e salve para associar o plano à extração atual. Enquanto isso, a análise automática permanece inconclusiva. A decisão humana continua separada.

Nova triagem iniciada depois da revisão pode substituir as extrações atuais; as anteriores ficam históricas. Salvar os mesmos dados de uma extração já revisada não cria outra revisão nem apaga decisão posterior. Editores que ficaram desatualizados são rejeitados. Cancelar ou fechar um editor alterado pede confirmação, e o fechamento do aplicativo também protege essa atividade.

O JSON inclui os estados atuais e o original automático preservado. O CSV de afirmações inclui `afirmacao_revisao`, `extracao_revisada`, `categoria_automatica`, `citacao_automatica`, justificativa/data da revisão e `plano_precisa_revisao`. O relatório usa a categoria atual da extração, incluindo reclassificações do operador, e continua sem estimar precisão ou cobertura das falas reais.

## Planejar a checagem

Em **Dossiê e fontes**, use **Planejar checagem** para registrar pergunta verificável, período, território, indicador ou fato a demonstrar, comparação, lacunas e URLs candidatas. Escolha a situação da pesquisa. Um pedido de explicação sem proposição explícita pode exigir descarte ou outra delimitação; essa avaliação não decorre apenas da etiqueta factual da IA.

Campos vazios permanecem a definir. A pergunta e os recortes do plano orientam as sugestões de busca, sem recolocar valores antigos do modelo onde o operador deixou campos vazios. As URLs candidatas passam pela validação institucional, mas não são acessadas nem arquivadas ao salvar. Colete ou importe uma fonte para obter conteúdo com localizadores, origem e data de acesso.

Rascunhos preparados pela IA ficam como **conferência humana pendente**. Salvar pelo operador registra essa origem no plano, sem conferir a transcrição ou decidir o veredito. Uma mudança tem revisão e histórico, limpa a análise e a decisão atuais e rejeita a conclusão de tarefas que usaram a versão anterior. As cópias de fontes permanecem disponíveis para reavaliar pertinência; nova coleta, análise ou retirada de fonte preservam o plano. Salvar dados idênticos não invalida resultados. Um editor concorrente não pode sobrescrever a versão mais recente.

O plano aparece no dossiê interno, em `dossiers.plan` no JSON e em colunas `plano_*` no CSV de afirmações. O relatório conta os planos das extrações atuais, incluindo as indefinidas. Uma sugestão de extração não verificável não altera a categoria nem descarta a afirmação; após conferir o caso, use **Descartar com justificativa** quando pertinente. A proporção de decisões continua usando apenas afirmações factuais atuais. A análise automática Gemini permanece inconclusiva quando depende de plano com contexto pendente, possível ausência de alegação verificável ou rascunho de IA sem conferência.

### Descobrir URLs candidatas

1. Abra uma afirmação atual em **Dossiê e fontes**, confira a pergunta e use **Encontrar fontes**.
2. Digite sua chave Tavily no campo mascarado. Essa chave é independente do Gemini e permanece só na memória; **Limpar chave** remove a configuração para próximas buscas. Uma requisição já enviada continua usando sua configuração até terminar.
3. Confira a consulta sugerida ou edite os termos e os recortes. **Buscar fontes** envia somente essa consulta à Tavily e solicita até cinco URLs institucionais no modo `basic`, sem resposta gerada ou conteúdo bruto. Não há busca de todos os parágrafos nem repetição automática.
4. Confira o título e a URL de cada candidata. **Usar URL para coleta** preenche o campo da fonte e fecha a janela; use **Coletar fonte** para obter o documento. A descoberta, sozinha, não cria evidência nem permite concluir sobre veracidade. O acesso à URL só é confirmado pela coleta posterior.
5. Se uma candidata não corresponder ao recorte, use **Descartar candidata** e justifique. O registro permanece. Buscas de versões anteriores ficam ocultas por padrão e podem ser consultadas pelo seletor de histórico; suas candidatas não podem ser usadas como atuais por essa janela.
6. **Cancelar busca** pede confirmação. Fechar a janela durante uma busca também exige confirmar o cancelamento. O fechamento do aplicativo aguarda a finalização da tarefa; uma requisição já enviada pode consumir cota mesmo se seu resultado for descartado.

Buscas e descartes ficam em tabelas próprias do SQLite, no dossiê interno e em `dossiers[].discoveries` no JSON. Não alteram o veredito humano ou a revisão factual do dossiê. Alterar fala, extração ou planejamento torna o contexto da busca anterior histórico e rejeita resultados antigos ainda em processamento. Os CSVs de fontes continuam contendo somente documentos coletados ou importados.

O modo local de triagem pode ser usado junto da busca Tavily. Sem essa chave, continue por **Buscar no navegador**, coleta por URL ou importação local. Limites, privacidade e cobrança dependem do seu contrato com o provedor; consulte a [documentação Tavily](https://docs.tavily.com/documentation/api-reference/endpoint/search). O aplicativo registra créditos apenas quando a API os informa, sem estimar reais ou saldo disponível.

O ensaio da versão 0.17 usou transporte simulado e dados fictícios. Verificou duas candidatas aceitas, descarte de URL fora da coleção, justificativa, seleção sem coleta automática e ausência da chave nos arquivos. A janela foi conferida em 1000 × 740 e 900 × 650; os diagramas foram renderizados sem textos fora dos cartões. Chamada real, disponibilidade e consumo da conta Tavily ainda dependem de uma chave e de validação operacional. Não houve nova inferência ou decisão sobre os casos políticos reais.

### Ensaio dos primeiros rascunhos na versão 0.14

Uma nova cópia da sessão usada na versão 0.13 recebeu outra execução dos três primeiros parágrafos, após ajustar a orientação de triagem e exigir campos não vazios na gramática local. Foram concluídos dois trechos; o inicial continuou rejeitado porque a citação gerada não corresponde ao texto salvo. Nenhuma correção de transcrição foi inventada. O pedido genérico de explicação passou a indefinido, e a alegação percentual passou a fato a pesquisar. Essas mudanças em uma amostra pequena não estimam precisão nem eliminam erros de segmentação ou classificação.

Foram preparados **quatro rascunhos de IA**: três com contexto pendente e um indicando possível ausência de alegação verificável. A página [Dados nacionais de segurança pública do MJSP](https://www.gov.br/mj/pt-br/assuntos/sua-seguranca/seguranca-publica/estatistica) foi baixada pela coleta real e gerou 23 blocos extraídos. Ela orienta a escolha de indicadores e metodologia; não comprova a tendência alegada no trecho. A candidata do TSE foi identificada em fonte oficial, mas a tentativa de coleta retornou PermissionError e não gerou evidência arquivada.

Os rascunhos preservam citação, categoria e atribuição da extração, distinguem fontes arquivadas de URLs candidatas e mantêm os nomes, períodos e recortes ausentes sem preenchimento por suposição. Não houve chamada a API de IA nem decisão humana. Os arquivos originais permaneceram iguais; a cópia, os dossiês e os relatórios estão em diretórios locais ignorados pelo Git. O próximo passo exige ouvir os trechos e definir o contexto dos casos antes de completar evidências e revisão factual.

## Ensaio editorial com gravação

1. Escolha um intervalo de três a cinco minutos com afirmações verificáveis, opiniões e frases que dependam de contexto. Registre vídeo, posição inicial, versão, operador e motor utilizado. Preserve o vídeo para rever a mesma fala.
2. Para preparar uma referência sem ver as sugestões, desmarque **Identificar afirmações automaticamente ao concluir cada parágrafo** antes da captura. Ouça e anote as afirmações elegíveis, com tempos e recortes. Separe essa referência das sugestões da IA; se usar revisão já assistida, registre essa condição.
3. Encerre a captura. Confira a transcrição, números, negações e participantes com o áudio. Registre correções necessárias, trechos ausentes e tempo gasto. As contagens automáticas do relatório não substituem essa conferência.
4. Execute a triagem nos parágrafos escolhidos. Compare as afirmações com a referência, incluindo as que a IA não identificou. Registre erros de extração, duplicações e tentativas rejeitadas. Uma resposta inválida permanece como falha; confira a fala antes de repetir a tentativa.
5. Para cada caso selecionado, use **Planejar checagem**, defina a pergunta e explicite recortes ausentes. Colete uma fonte institucional ou importe uma cópia já baixada, conferindo a URL declarada. Verifique período, território, indicador, método e possíveis fontes divergentes. Uma cópia importada não comprova acesso à URL.
6. Se optar por Gemini, configure e teste sua chave antes da análise preliminar. Sem API, a equipe pode ler as fontes e revisar manualmente. Registre a decisão humana e a justificativa somente após a conferência; casos sem evidência suficiente podem permanecer inconclusivos. Não há publicação automática.
7. Exporte o JSON completo, os CSVs necessários e **Relatório do ensaio · TXT/JSON**, usando **Exportar sessão**. Abra os arquivos no destino e confira campos, texto, fontes e estados. O relatório usa as afirmações atuais; tentativas antigas ficam separadas, inclusive depois de uma nova tentativa bem-sucedida.
8. Preencha a ficha abaixo com a referência humana e as observações. Compare esforço, cobertura e falhas, mantendo o denominador das afirmações reais separado da quantidade detectada pela IA. Defina as correções e os limites aceitáveis antes de repetir ou avançar para um evento ao vivo.

### Como ler os tempos e denominadores

| Medida | Interpretação e limite |
| --- | --- |
| Decisões humanas / factuais atuais | Usa apenas extrações atuais e não descartadas classificadas como factuais, incluindo reclassificações do operador. Não mede precisão nem recuperação das afirmações reais. Sem factuais atuais, a proporção fica indisponível. |
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
