# Checklist de desenvolvimento do sistema de checagem em debates políticos ao vivo

**Versão 0.1 · 22 de outubro de 2026 · Plano do MVP**

Este checklist organiza o trabalho necessário para desenvolver, testar e avaliar o primeiro piloto de checagem assistida por IA em um debate político ao vivo. A equipe humana validará os dossiês e decidirá sobre qualquer divulgação; o piloto será de uso interno.

O plano contém **15 fases de execução, 124 tarefas pendentes e 6 entregas concluídas**. As escolhas de tecnologias, evento, equipe, orçamento e metas serão feitas nas tarefas correspondentes.

### Andamento do primeiro incremento

A equipe de desenvolvimento é formada pelo proponente e pelo Codex. A distribuição das responsabilidades humanas de operação, revisão e decisão editorial continua a ser definida para o piloto.

Por orientação do proponente, o desenvolvimento começou com um experimento de captura da saída de áudio do Windows e transcrição local. O protótipo permite selecionar a saída, acompanhar o nível, iniciar e encerrar a gravação e ler trechos com horários. A primeira captura real de vídeo salvou 20,011 segundos de áudio estéreo a 48 kHz, sem falhas sinalizadas pelo dispositivo; o texto gerado ainda exige revisão. As demais entregas da fase 06 continuam pendentes.

A página privada preserva a versão inicial de planejamento. Este arquivo e o README registram o andamento técnico atual até sua próxima reconciliação com a página.

Na versão 0.2, o primeiro envio de áudio passou para dois segundos, com atualizações a cada três segundos e contexto de até seis segundos. O botão **Cancelar sessão** exige confirmação, cancela pendências e preserva os arquivos já gravados. A validação inclui os caminhos de confirmação aceita e recusada e a diferenciação entre cancelar e encerrar normalmente.

Na versão 0.3, o modo padrão passou a usar reconhecimento contínuo local, recebendo pacotes de 0,2 segundo. A interface separa hipóteses provisórias de trechos estabilizados; somente os estabilizados são persistidos, sempre com revisão humana pendente. O modo Whisper permanece disponível para comparação. O ensaio com o vídeo já salvo, alimentado no ritmo original, entregou a primeira prévia em 1,54 segundo, excluindo preparação, captura e atualização visual. Os 35 testes passaram, incluindo cancelamento nos dois motores e interrupção segura do reconhecimento quando há falha ou fila cheia. A avaliação de precisão com referência humana e as metas de aceitação da fase 06 permanecem pendentes; pacotes de 0,2 segundo não garantem texto pronto nesse intervalo.

Na versão 0.4, a interface passou a agrupar trechos em parágrafos por pausas e regras locais de continuidade da frase, com pausa ajustável, pontuação sugerida e opção de consultar o texto original. Os arquivos **paragraphs.txt** e **paragraphs.jsonl** preservam a versão de leitura e o histórico com ligação aos trechos originais. A janela exige confirmação ao fechar com uma sessão ativa e aguarda o cancelamento e a finalização dos arquivos; tarefas adicionais registradas, incluindo uma checagem simulada, também entram nessa proteção. A checagem real e a identificação automática de falantes continuam pendentes. Os testes cobrem preservação de comparações, negações e complementos, fechamento recusado e confirmado e preservação dos parágrafos ao cancelar.

Na versão 0.5 foram implementados o cadastro de debate e participantes, abertura de sessões gravadas, reprodução do áudio de um parágrafo, correção de texto e atribuição manual de falante. Um banco SQLite por sessão preserva revisões e invalida análises dependentes. A triagem local com Qwen3-4B separa declarações factuais, opiniões, promessas e falas indefinidas, com citações ligadas à versão analisada e campos de contexto. A fila mostra progresso, falhas e cancelamentos; ainda não realiza pesquisa nem conclui sobre veracidade. A configuração com GPU foi testada junto com a transcrição, e 85 testes automatizados cobrem os controles. A avaliação editorial com referência humana das fases 02 e 07 segue pendente; esses ensaios não concluem a fase de triagem.

Na versão 0.6, por solicitação do proponente, a API Gemini passou a ser uma opção de triagem, mantendo o modo local como escolha inicial. A configuração explicita o envio de texto ao Google e o tratamento de dados na camada gratuita. A chave digitada permanece na memória; o histórico registra o modelo e o uso informado pela API. A fila limita o ritmo de chamadas e interrompe os envios em caso de cota esgotada ou erro. Os 99 testes passaram com transporte Gemini simulado, cobrindo validação das citações, cancelamento, falhas de rede e proteção da chave. A chamada real depende da configuração de uma chave pelo proponente; disponibilidade, cotas e latência do projeto ainda precisam de validação. A geração de texto pela API não implementa pesquisa de evidências nem conclui as fases 07 e 08.

Na versão 0.7 foi implementada a aba **Dossiê e fontes**: consultas orientadas abertas no navegador, coleta por URL de páginas e PDFs institucionais, cópia textual com localizadores e metadados, análise preliminar opcional pelo Gemini e decisão humana separada. O armazenamento versionado invalida conclusões após alterações e rejeita resultados antigos; a retirada de fontes exige motivo e preserva a cópia no histórico. A exportação é interna, sem publicação automática. Os 130 testes passaram, incluindo extração de documentos fictícios pelas bibliotecas reais, restrições de URL/DNS/redirecionamentos, citações, revisões concorrentes, cancelamento tardio e interface. O fluxo com extração em processo Windows real foi exercitado com transporte simulado e a nova tela foi inspecionada visualmente. A coleta HTTP real foi bloqueada no ambiente gerenciado pelo WinError 10013; o acesso pela interface na execução normal e as chamadas reais ao Gemini continuam pendentes. Busca automática de links, OCR, validação de tabelas complexas, independência de evidências e avaliação editorial ainda precisam de desenvolvimento e ensaios. Por isso, as fases 08, 09 e 11 não são consideradas concluídas.

Na versão 0.8 foram adicionados o **Teste de conexão** da chave Gemini, com uma chamada fictícia e sem envio de falas, e a **Importação de PDF/HTML** sem acesso à rede. O teste não aplica a configuração, permite cancelamento e ignora respostas relativas a uma chave alterada. A importação exige URL institucional declarada, guarda metadados e marca a cópia como fornecida pelo operador; não afirma que a URL foi consultada. Análises dependentes dessas cópias ficam inconclusivas até a avaliação humana da origem. A coleta online posterior pode atualizar a origem e invalida a decisão anterior. Os 146 testes passaram, cobrindo essas operações, diagnósticos de rede e extração local de HTML/PDF em processo Windows real, sem alterar os arquivos originais. A chamada real ao Gemini e a validação operacional da coleta online continuam pendentes; as novas opções permitem executar e diagnosticar esses ensaios sem alterar a avaliação das fases ainda abertas.

Na versão 0.9 foi implementada a **Minutagem do vídeo**, com posição manual correspondente ao início da captura, exibição paralela dos tempos originais e de referência e uso nos detalhes das afirmações e no dossiê interno. A configuração é independente do cadastro e da revisão factual, fica versionada no SQLite e é recuperada ao reabrir; uma nova sessão começa sem referência. Ajustar a minutagem não altera o áudio, as falas nem as decisões humanas. Os 159 testes passaram, incluindo migração de bancos anteriores, concorrência na referência, preservação de análise em andamento e reprodução do áudio original. A nova janela e as telas de captura e revisão foram inspecionadas com dados fictícios. A sincronização manual com um player real, a coleta online e a chamada real ao Gemini continuam pendentes de validação operacional. Combinação reversível e exportação estruturada seguem no plano.

Na versão 0.10 foram adicionados **Combinar com o próximo** e **Descombinar** na revisão de falas. A operação preserva originais, correções, intervalos de áudio e histórico, impede unir participantes diferentes e exige conferir autoria indefinida. O combinado recebe identificação própria, pode ser combinado novamente e é recuperado ao reabrir; os componentes permanecem no banco. A reversão de um texto alterado exige distribuição e conferência manual, sem omitir palavras. Atualizações tardias da origem bloqueiam a triagem do combinado até reconciliação. Análises e dossiês afetados ficam desatualizados, com decisões anteriores preservadas, e a operação não dispara outra análise automaticamente. Os 183 testes passaram; as telas foram inspecionadas com dados fictícios, incluindo a divisão de uma correção e a preservação do áudio. A avaliação editorial durante um debate real continua pendente; a entrega não conclui as fases 06, 07, 10 ou 11.

Na versão 0.11 foi implementada **Exportar sessão**, com JSON completo e CSVs separados de falas, afirmações e fontes. Os arquivos incluem identidades persistentes, referências de origem, tempos e estados, distinguindo análise preliminar e decisão humana. A seleção padrão mantém falas atuais, opiniões e promessas; itens substituídos, descartados e desatualizados são opcionais. As origens necessárias das combinações acompanham o JSON. Uma transação única produz o retrato e a escrita usa temporário com substituição ao concluir, confirmação de cancelamento e proteção de fechamento. Os 208 testes passaram, incluindo coerência com edição concorrente, reexportação, migração, hashes, proteção dos campos CSV e preservação do arquivo anterior após falha ou cancelamento. As novas telas foram inspecionadas com dados fictícios. A abertura em planilhas, o ensaio de recuperação e a avaliação editorial continuam pendentes. A exportação é interna; conectores de envio e confirmação de recebimento seguem propostos.

Na versão 0.12 foi implementado **Estado da sessão**, com diagnóstico da captura, registros persistidos, áudio disponível e pendências. Os metadados usam substituição completa; o cabeçalho WAV é atualizado por pacote. A abertura tolera somente a cauda JSONL inválida sem quebra final, com aviso e preservação dos originais; corrupção intermediária bloqueia a importação. É possível criar uma cópia recuperada do WAV e encerrar parágrafos com confirmação, revisão própria e conferência humana pendente. Os **231 testes passaram**, incluindo encerramento forçado de subprocesso próprio com PCM e registros fictícios, reversão de transação SQLite não confirmada, preservação da revisão e decisão humana, cancelamento e bloqueios da interface. O [guia de operação e recuperação](operacao-e-recuperacao.md) registra procedimento, ensaio e limitações. A recuperação técnica local não conclui backup, ensaio editorial ou liberação ao vivo; as fases 12 e 13 permanecem abertas.

Na versão 0.13 foi implementado **Relatório do ensaio**, em JSON e TXT, pela exportação existente. O resumo separa tentativas históricas de afirmações atuais, pendências de fontes e decisão humana, registra denominadores e mantém métricas de qualidade indisponíveis sem referência humana. Novas capturas registram a primeira prévia e a entrega dos segmentos estabilizados; sessões antigas não recebem medições inventadas. Os **251 testes passaram**, incluindo versões desatualizadas, agrupamentos, logs parciais, cancelamento e interface. Em uma cópia de gravação real com 336,341 s e 22 parágrafos, o relatório preservou os originais e a ausência de medições antigas. A triagem local dos três primeiros parágrafos concluiu dois, rejeitou um por citação inválida e gerou três itens factuais, quatro opiniões e um indefinido. Nenhuma chamada a API foi feita. Fontes, revisão humana e avaliação de precisão dessa amostra permanecem pendentes; a falha não foi ocultada por repetição automática. O [guia do ensaio](operacao-e-recuperacao.md#ensaio-editorial-com-gravação) documenta leitura e próximos passos. A entrega não conclui as fases 12 ou 13.

Na versão 0.14 foi implementado **Planejar checagem**, com pergunta, recortes, lacunas, situação e URLs candidatas, distinguindo rascunhos de IA de planos salvos pelo operador. O plano tem revisão e histórico, invalida conclusões dependentes quando muda, preserva fontes e rejeita resultados antigos. Os **270 testes passaram**, incluindo concorrência, campos ausentes, preservação da citação, separação de fontes candidatas, exportação, relatórios e interface. A orientação de triagem foi atualizada e a gramática local passou a exigir campos não vazios. A nova execução dos três trechos concluiu dois; o primeiro continuou rejeitado por citação não literal. Foram preparados quatro rascunhos, três com contexto pendente e um possivelmente não verificável. A coleta real de uma página do MJSP gerou 23 blocos como referência metodológica; a candidata do TSE não foi arquivada após PermissionError. Nenhuma API de IA foi chamada ou decisão humana registrada. Originais, versões antigas e tentativas rejeitadas permaneceram preservados. Precisão, contexto dos casos e revisão factual continuam pendentes; a entrega não conclui as fases 07 a 11 ou o ensaio editorial.

Na versão 0.15 foi implementado **Revisar afirmação**, com edição de citação literal, resumo, categoria e tema e justificativa obrigatória. Cada extração tem identidade e revisão próprias; o conteúdo automático e as revisões intermediárias são preservados. A mudança invalida análises e decisões dependentes, marca o plano para conferência e rejeita tarefas e editores antigos. Os **290 testes passaram**, incluindo reclassificação, negações, duplicação, concorrência, migração de registros sem versão, preservação de fontes e histórico, relatórios, exportações e interface. A tela foi exercitada com uma opinião fictícia extraída como factual. Não houve nova inferência nem marcação dos casos reais como revisados. Descoberta automática de fontes, filtros, prioridades e identificação de falantes continuam como entregas técnicas, em paralelo à avaliação humana; essa entrega não conclui as fases 07 a 11.

Na versão 0.16 foram implementados **filtros locais da fila** por texto, escopo atual/histórico, categoria, estado, participante e tema. Eles combinam critérios, distinguem campos vazios e preservam os registros e o escopo de exportação. A seleção desaparece quando o item sai do filtro; alterações de metadados não removem silenciosamente uma restrição selecionada. Os **302 testes passaram**, cobrindo correspondência sem acentos, versões antigas, estados de dossiê, preservação dos dados e edição sob filtro. A interface foi conferida com dados fictícios em 1120 × 860 e 1000 × 760. Foram criados e renderizados dois SVGs, de [funcionamento interno](diagramas/fluxo-interno.svg) e [jornada do usuário](diagramas/fluxo-usuario.svg), com funções futuras tracejadas. Não houve envio de falas, nova inferência ou revisão dos casos reais. Prioridades, responsáveis, busca automática e identificação de falantes seguem pendentes; a fase 11 não está concluída.

Na versão 0.17 foi implementado **Encontrar fontes**, com consulta Tavily opcional, chave do usuário somente na memória, até cinco URLs institucionais e uma requisição por clique, sem retentativa automática. Consulta, horário, créditos informados, candidatas e descartes têm registro próprio no SQLite, dossiê interno e JSON. A descoberta não cria evidências, altera decisão humana ou habilita análise sem documentos. Alterações de fala, extração e planejamento preservam buscas anteriores como históricas e rejeitam respostas antigas; a seleção de uma URL apenas prepara a coleta. Os **326 testes passaram**, incluindo validação do transporte simulado, cancelamento, cota, segredo, histórico e preservação de decisões. A janela foi conferida em dois tamanhos e os dois diagramas atualizados e renderizados. Chamada real, disponibilidade e consumo da conta ainda precisam de validação com chave. Pesquisa contínua, fontes preparadas e reutilização de checagens seguem pendentes; a fase 08 permanece aberta.

Na versão 0.18 foi implementado **Definir prioridade**, com níveis manuais Alta, Normal, Baixa e Não definida, justificativa obrigatória e revisão própria com histórico. A fila permite filtrar prioridades e ordenar os casos atuais antes dos históricos; atribuições que dependem de uma extração alterada ficam a conferir. Novas triagens não herdam prioridades. Fontes, planos, decisões e tarefas permanecem independentes. Os **352 testes passaram**, incluindo concorrência, remoção, reabertura, bancos antigos, filtros, ordenação, exportações, relatórios e preservação factual. A fila e o editor foram conferidos em dois tamanhos cada; os SVGs foram atualizados e renderizados. O ensaio usou dados fictícios, sem chamadas externas ou decisões sobre os casos políticos reais. Responsáveis, critérios editoriais avaliados e escalonamento de tarefas por prioridade continuam pendentes; as fases 07, 10 e 11 permanecem abertas.

## Prioridades para a operação ao vivo

**Planejamento atualizado em 23 de outubro de 2026; acompanhamento da implementação: versão 0.18.**

A análise de um fluxo de desenvolvimento paralelo trouxe necessidades úteis para nosso piloto. Esta seção registra requisitos gerais, sem reproduzir mensagens, dados pessoais ou acessos do material privado. Os relatos não constituem uma auditoria da outra aplicação; imagens, vídeos e áudios omitidos na exportação não foram avaliados. A proposta mantém os produtos independentes, com transcrição e triagem locais e Gemini opcional no Fact-Check AI.

| Necessidade observada | Situação no Fact-Check AI 0.18 | Melhoria proposta |
| --- | --- | --- |
| Encontrar a fala na transmissão | Tempos da captura, reprodução do áudio salvo e referência manual do vídeo por sessão. | Validar sincronização com um player real e tratamento operacional de descontinuidades. |
| Corrigir cortes entre falas | Agrupamento automático e combinação reversível na revisão, com originais, correções e histórico preservados. | Avaliar a segmentação e o esforço de revisão com referência humana. |
| Continuar após falhas | Diagnóstico de retomada, importação com aviso de cauda incompleta, cópia recuperada de WAV e encerramento manual de parágrafos. Ensaio de queda em subprocesso preservou revisão e decisão humana. | Validar com vídeo representativo, backup e troca de operador. Não há retomada automática da transmissão. |
| Medir o ensaio | Relatório JSON/TXT com tempos registrados, denominadores, tentativas históricas e pendências atuais. Primeira prévia e entrega estabilizada passam a ser registradas nas novas capturas. | Conferir transcrição, precisão, cobertura e esforço com referência humana; completar fontes e decisão factual. |
| Definir o que pesquisar | Planejamento versionado por dossiê, com pergunta, recortes, lacunas e URLs candidatas, separado de citação e decisão. | Conferir o áudio, identificar pessoas e datas e completar a pesquisa sem presumir contexto. |
| Descobrir fontes | Busca Tavily sob demanda, com chave em memória e histórico de candidatas e descartes; coleta posterior escolhida pelo operador. | Validar chamada real, pertinência e consumo; ampliar provedores e pesquisa contínua depois dos ensaios. |
| Corrigir a extração da IA | Editor de citação, resumo, categoria e tema, com justificativa, revisão própria e preservação do automático; filtros locais para localizar itens. | Avaliar erros e esforço de correção com referência humana e a consistência da priorização manual. |
| Trocar material entre ferramentas | Exportação estruturada em JSON e CSV, com identidades, origens e estados; dossiê interno em Markdown. | Validar consumo em outras ferramentas e depois implementar conectores opcionais com confirmação de recebimento. |
| Distribuir o trabalho | Prioridade manual com justificativa, revisão, histórico, conferência após edição da extração, filtros e ordenação da lista. | Atribuição de responsáveis, critérios editoriais avaliados e escalonamento das tarefas por prioridade. |
| Reutilizar preparação editorial | Fontes adicionadas por URL ou importadas manualmente. | Coleção pesquisável de fontes e checagens anteriores, com validade temporal. |
| Padronizar análises | Metodologia proposta e instruções dos modelos no código. | Manual editorial versionado, exemplos e avaliação contra referência humana. |

### Sequência proposta de desenvolvimento

1. **Validar a operação atual.** Exercitar uma chave Gemini com o botão de teste e uma coleta online na execução normal do Windows; testar também o caminho local e a importação de documentos. Registrar versão, resultados e limitações antes de um evento real. A rede e a chamada real à API continuam pendentes de validação. Relacionado a **04.03, 12.04, 13.01 e 14.04**.
2. **Minutagem de referência — implementada na versão 0.9.** Permite informar a posição do vídeo correspondente ao início da captura. Exemplo: captura iniciada no minuto 12:30 do vídeo; um parágrafo aos 30 segundos da sessão corresponde a 13:00. Os tempos originais são preservados e as alterações da referência ficam registradas. A referência pode ser ajustada durante a gravação e não é herdada por novas sessões. Pausas ou saltos no player exigem outra sessão; o aplicativo não conhece automaticamente a posição do player. A validação operacional dessas correspondências continua pendente. Relacionado a **03.04, 06.04 e 06.09**.
3. **Combinar e descombinar parágrafos — implementado na versão 0.10.** A revisão permite unir blocos adjacentes e concluídos, inclusive durante a captura, com identificação própria e preservação dos componentes. Participantes diferentes são bloqueados e a autoria indefinida exige conferência. Combinar e desfazer invalidam as análises dependentes; o histórico e as decisões anteriores são preservados. Após alterações no combinado, a reversão exige distribuir o texto e conferir sua preservação. Combinações sucessivas podem ser desfeitas uma etapa por vez. A avaliação editorial do fluxo continua pendente. Relacionado a **03.06, 06.08, 07.04 e 10.07**.
4. **Exportar para uso interno em outras ferramentas — implementado na versão 0.11.** JSON preserva relações, revisões, origens e texto extraído das fontes; cada CSV contém uma tabela de falas, afirmações ou fontes. O formato inclui identidades do evento e da sessão, referência de vídeo, estados editoriais e hashes para comparar retratos e registros. Reexportar mantém os identificadores e distingue mudança de conteúdo. CSVs usam proteção para textos que podem iniciar fórmulas; JSON mantém o texto literal. A validação nas planilhas e ferramentas de destino continua pendente. Conectores de envio são uma etapa posterior, com confirmação de recebimento e prevenção de duplicação nas retentativas. Relacionado a **03.03, 03.04, 07.06, 10.05 e 11.09**.
5. **Recuperação técnica implementada e ensaiada na versão 0.12; operação editorial pendente.** A tela **Estado da sessão** explicita dados disponíveis e tarefas interrompidas, oferece cópia do WAV quando necessário e encerramento confirmado dos parágrafos sem completar falas perdidas. Um subprocesso próprio com PCM e registros fictícios foi encerrado à força; o ensaio conferiu reversão de transação não confirmada, preservação da revisão humana e decisão do dossiê, áudio disponível, exportação e reabertura repetível. O [procedimento de operação e recuperação](operacao-e-recuperacao.md) permite repetir o teste e registrar o próximo ensaio. Usar uma gravação conhecida com referência humana para medir primeira prévia, estabilização, cobertura factual e tempo até o dossiê revisado. Comparar as aplicações independentes com o mesmo conteúdo continua proposto. Duas capturas servem como redundância, mas não garantem troca automática de operador nem eliminação de duplicações entre máquinas. Relacionado a **04.01, 06.02, 12.06 e 13.06 a 13.09**.

6. **Relatório do ensaio — implementado na versão 0.13.** Resume registros atuais e históricos em JSON/TXT, com contagens, denominadores, tempos disponíveis, avisos e pendências. O relatório foi gerado sobre cópia de gravação real e depois de três tentativas de triagem local, incluindo uma rejeitada. Precisão e cobertura contra as falas reais continuam indisponíveis até a referência humana. Usar o [roteiro do ensaio editorial](operacao-e-recuperacao.md#ensaio-editorial-com-gravação) para completar fontes e decisões e comparar trabalho manual e assistido. Relacionado a **12.01, 12.08 e 13.07 a 13.10**.

7. **Planejamento dos dossiês — implementado na versão 0.14.** Permite formular pergunta e recortes antes de avançar na pesquisa, mantendo lacunas explícitas e fontes candidatas separadas das coletadas. Mudanças têm revisão, invalidam conclusões dependentes e preservam o histórico. Quatro rascunhos e uma referência metodológica efetivamente coletada exercitaram o fluxo em cópia de gravação real. Ouvir os trechos e definir pessoas, data do evento e períodos continua necessário antes de completar os casos. Relacionado a **03.06, 07.04, 08.01 e 11.04**.

8. **Revisão das extrações — implementada na versão 0.15.** O operador pode corrigir categoria, resumo, tema e recorte literal sem alterar a transcrição nem decidir a veracidade. As mudanças têm revisão e histórico, afetam a fila atual e invalidam análises, decisões e tarefas que usaram a extração anterior. O plano fica a conferir, e os dados exportados distinguem o automático da revisão. Relacionado a **07.04, 10.07 e 11.07**.

9. **Filtros da fila — implementados na versão 0.16.** Busca local e seleção combinada de escopo, categoria, estado, participante e tema. A visualização distingue registros atuais e históricos e não altera o banco, inicia análises ou restringe exportações. Há limpeza de seleção quando um item deixa de corresponder e reinicialização ao abrir outra sessão. A prioridade manual foi acrescentada na versão 0.18; responsáveis continuam pendentes. Relacionado a **11.02**, que permanece parcialmente atendida.

10. **Descoberta de fontes sob demanda — implementada na versão 0.17.** A busca Tavily recebe a consulta conferida pelo operador e retorna candidatas institucionais, sem tratá-las como evidências. Há chave própria em memória, limites, cancelamento, descarte justificado e histórico. Coleta e análise continuam como etapas separadas. A busca não usa o grounding Gemini, cujos termos restringem a extração de links para coleta. Chamada real e avaliação da pertinência continuam pendentes. Relacionado a **04.03, 08.02 e 10.04**, parcialmente atendidas.

11. **Prioridade manual da revisão — implementada na versão 0.18.** O operador atribui um nível com justificativa e pode remover ou reconfirmar a prioridade, com revisão própria e histórico. A lista oferece filtro e ordenação por prioridade; uma extração alterada exige conferência e uma nova triagem começa sem atribuição. A prioridade acompanha JSON, CSV, dossiê e relatório, preservando estados e tarefas factuais. Responsáveis e escalonamento automático continuam pendentes. Relacionado a **07.05, 10.03 e 11.02**, parcialmente atendidas.

O plano de incrementos reúne **minutagem de referência, combinação reversível, exportação estruturada, recuperação local, relatório do ensaio, planejamento dos dossiês, revisão das extrações, filtros da fila, descoberta de fontes sob demanda e prioridade manual**, implementadas nas versões 0.9 a 0.18. A validação automatizada cobre persistência, áudio sem deslocamento, preservação das revisões, rejeição de análises antigas, exportação repetível, retomada após queda do processo, métricas com denominadores explícitos, revisão de planos e extrações, filtros e ordenação locais, prioridade independente do veredito e busca com transporte simulado. Os [diagramas](diagramas/README.md) representam esses fluxos e identificam a evolução planejada. O ensaio operacional completo e a avaliação editorial continuam pendentes; essas entregas técnicas não constituem liberação para uso ao vivo.

### Evolução editorial e integração opcional

Depois desse incremento, priorizar vocabulário configurável de temas, atribuição de responsáveis, coleção de fontes preparadas e busca de checagens anteriores. Os filtros da versão 0.16 usam os temas livres já cadastrados; a 0.17 encontra URLs sob demanda pela Tavily e a 0.18 acrescenta prioridade manual. Correspondência textual em uma planilha apenas indica material candidato: reutilizar uma conclusão exige conferir período, território, indicador, método e documentos de suporte. A pesquisa contínua e os demais recursos da fase 08 permanecem pendentes.

As próximas entregas técnicas podem avançar em paralelo ao ensaio humano: responsáveis, distribuição e escalonamento das tarefas; coleção de fontes e checagens anteriores; tratamento de falhas e repetições; pesquisa contínua e outros provedores; e separação de falantes com atribuição aos participantes. A avaliação humana informa essas escolhas, sem interromper o desenvolvimento dos recursos ainda pendentes.

O manual editorial deve definir o recorte das afirmações, a preservação de negações e qualificadores, os critérios de fonte e as condições para concluir ou se abster. Registrar sua versão em cada análise e avaliá-lo com casos revisados por pessoas antes de ampliar a automação. Relacionado às fases **02, 07, 08 e 09**.

Manter independentes os estados de **reconhecimento estabilizado**, **transcrição conferida**, **análise preliminar** e **decisão humana**. Aprovar uma transcrição ou aceitar um rascunho não valida a afirmação nem autoriza divulgação. Uma futura integração por API ou MCP deve respeitar esses estados e permissões; a decisão editorial continua humana. O produto não precisa depender de uma planilha, de MCP ou da outra plataforma para funcionar.

Esta seção detalha e prioriza tarefas existentes; não altera a contagem nem marca fases como concluídas.

## Como acompanhar a execução

Uma caixa vazia indica uma tarefa pendente; uma caixa marcada indica uma entrega concluída. Para marcar um item, registrar a entrega correspondente e a verificação realizada. Bloqueios, responsável individual e previsão de conclusão deverão acompanhar a tarefa quando sua execução começar.

Os números das tarefas permitem referenciá-las no acompanhamento do projeto. O responsável de cada fase indica um papel sugerido; a distribuição entre pessoas será definida na fase 01.

As dependências indicam os pré-requisitos para concluir uma fase. Desenho de telas e desenvolvimento com dados simulados podem começar antes de todas as integrações; a aceitação exige o fluxo real. Após a base técnica, transcrição, triagem e pesquisa podem avançar em paralelo, respeitando seus contratos de dados.

A proposta inicial estabelece o escopo; este checklist detalha sua execução. O ensaio com gravação prepara o piloto ao vivo.

## 00 Preparação já concluída

- [x] **00.01** Registrar a proposta inicial do projeto.
- [x] **00.02** Definir o primeiro caso de uso como debate político ao vivo, com decisão final humana.
- [x] **00.03** Organizar a documentação na pasta do projeto e disponibilizar a proposta em página privada.

## Visão das fases

| Fase | Entrega principal | Depende das fases |
| --- | --- | --- |
| 01 | Definir o piloto e organizar a equipe | 00 |
| 02 | Definir a metodologia e preparar a avaliação | 01 |
| 03 | Desenhar a experiência e os contratos de dados | 01, 02 |
| 04 | Comparar serviços e escolher as tecnologias | 02, 03 |
| 05 | Preparar a base do projeto | 03, 04 |
| 06 | Implementar captura de áudio e transcrição | 05 |
| 07 | Implementar a triagem de afirmações | 02, 05 |
| 08 | Implementar pesquisa e gestão de evidências | 02, 05 |
| 09 | Implementar análise e geração dos dossiês | 07, 08 |
| 10 | Coordenar os agentes e o processamento | 06, 07, 08, 09 |
| 11 | Construir o painel de revisão humana | 03, 05, 10 |
| 12 | Preparar monitoramento e operação | 05, 10, 11 |
| 13 | Validar o sistema em ensaio completo | 02, 06, 07, 08, 09, 10, 11, 12 |
| 14 | Preparar e executar o piloto ao vivo | 01, 13 |
| 15 | Avaliar o piloto e planejar a próxima versão | 14 |

## 01 Definir o piloto e organizar a equipe

**Responsável sugerido:** Proponente e editor. **Dependências:** 00.

- [ ] **01.01** Selecionar o debate político ao vivo, a data e a origem da transmissão.
- [ ] **01.02** Confirmar idioma, participantes, duração prevista e condições de acesso ao áudio.
- [ ] **01.03** Definir quem opera a transmissão, quem revisa os dossiês e quem responde pela decisão editorial.
- [ ] **01.04** Descrever o fluxo de trabalho atual da equipe e as principais dificuldades durante debates.
- [ ] **01.05** Registrar os casos de uso do MVP e os limites de cobertura esperados para uma única transmissão.
- [ ] **01.06** Definir orçamento máximo, disponibilidade da equipe e capacidade simultânea de revisão.
- [ ] **01.07** Registrar decisões, responsáveis, dependências e estimativas das entregas antes de iniciar a implementação.
- [ ] **01.08** Definir o procedimento de interrupção do piloto e de continuidade da checagem manual.

**Fase concluída quando:** Evento, equipe, escopo, limites operacionais e orçamento registrados; cada papel possui um responsável.

## 02 Definir a metodologia e preparar a avaliação

**Responsável sugerido:** Editor e revisores. **Dependências:** 01.

- [ ] **02.01** Escrever as regras para distinguir fatos verificáveis, opiniões, promessas e frases ambíguas.
- [ ] **02.02** Definir as classificações confirmada, contradita, precisa de contexto e inconclusiva, com exemplos e critérios para resolver sobreposições.
- [ ] **02.03** Definir critérios de prioridade e descarte aplicáveis igualmente a todos os participantes.
- [ ] **02.04** Selecionar gravações e transcrições representativas para ensaios, incluindo falas sobrepostas, números e temas diversos.
- [ ] **02.05** Anotar afirmações, participantes, contexto, fontes e conclusões esperadas; registrar divergências entre os revisores.
- [ ] **02.06** Separar material de desenvolvimento e de avaliação, evitando que a mesma afirmação ou repetição equivalente apareça nos dois conjuntos.
- [ ] **02.07** Registrar o corte temporal de cada gravação e distinguir evidências disponíveis na época de informações posteriores.
- [ ] **02.08** Definir métricas e como medir o trabalho manual, o assistido e a espera na fila, incluindo casos sem resposta.
- [ ] **02.09** Definir critérios de aceitação, gravidade das falhas e processo para fixar os limites numéricos após o ensaio e antes do piloto.

**Fase concluída quando:** Metodologia, conjunto de referência humana e plano de medição preparados para avaliar o protótipo.

## 03 Desenhar a experiência e os contratos de dados

**Responsável sugerido:** Produto, revisores e equipe técnica. **Dependências:** 01, 02.

- [ ] **03.01** Desenhar as telas de evento, transcrição, fila de afirmações, dossiê e revisão com os futuros usuários.
- [ ] **03.02** Validar o percurso de conferir a fala, abrir evidências, pedir pesquisa adicional e concluir a revisão.
- [ ] **03.03** Definir os registros de evento, participante, trecho, afirmação, documento, evidência, análise e decisão humana.
- [ ] **03.04** Especificar os campos obrigatórios, identificadores, datas, marcações de tempo e vínculos entre os registros.
- [ ] **03.05** Separar estados de processamento, estados de revisão e classificações da IA e do revisor.
- [ ] **03.06** Definir como uma correção da fala ou das evidências gera nova versão e exige revalidação.
- [ ] **03.07** Especificar interfaces entre componentes, permissões por papel e pontos de medição de tempos e custos.

**Fase concluída quando:** Telas essenciais e formatos de entrada e saída definidos, com exemplos de dossiê completo e incompleto.

## 04 Comparar serviços e escolher as tecnologias

**Responsável sugerido:** Equipe técnica com revisão editorial. **Dependências:** 02, 03.

- [ ] **04.01** Preparar uma comparação de transcrição usando as mesmas amostras em português e as mesmas condições de áudio.
- [ ] **04.02** Comparar modelos de identificação e análise com foco em fidelidade à fala, vínculo com evidências, abstenção e tempo de resposta.
- [ ] **04.03** Comparar mecanismos de busca e recuperação, verificando acesso real ao documento e localização dos trechos.
- [ ] **04.04** Estimar custo por hora de evento e por dossiê, incluindo repetições, falhas e novas tentativas.
- [ ] **04.05** Verificar limites dos serviços e condições de uso, retenção e tratamento do material enviado.
- [ ] **04.06** Escolher as tecnologias do painel, serviço de coordenação, fila, banco de registros e armazenamento.
- [ ] **04.07** Registrar as escolhas, alternativas e motivos, mantendo os conectores de transcrição, busca e modelos substituíveis.

**Fase concluída quando:** Tecnologias selecionadas com evidências dos experimentos, limites conhecidos e estimativa inicial de custo.

## 05 Preparar a base do projeto

**Responsável sugerido:** Equipe técnica. **Dependências:** 03, 04.

- [x] **05.01** Criar a estrutura do código e o controle de versão, preservando a documentação existente.
- [x] **05.02** Configurar ambiente local, ambiente de testes e instruções reproduzíveis para iniciar o projeto.
- [ ] **05.03** Configurar credenciais por ambiente e impedir que segredos apareçam no código, nos dossiês ou nos registros exportados.
- [ ] **05.04** Criar os registros e as migrações do banco conforme os contratos de dados.
- [ ] **05.05** Preparar o armazenamento de mídia e documentos, com identificação de versões e regras de retenção.
- [ ] **05.06** Implementar autenticação e autorização no serviço para operador, revisor, editor e processos automatizados.
- [ ] **05.07** Configurar verificação automática do código e testes dos controles centrais em cada alteração.
- [ ] **05.08** Adicionar identificadores de rastreamento, registros de execução e contabilização básica de uso desde o início.

**Fase concluída quando:** Projeto inicializável e componentes básicos disponíveis, com persistência, permissões e rastreabilidade funcionando.

## 06 Implementar captura de áudio e transcrição

**Responsável sugerido:** Equipe técnica e operador. **Dependências:** 05.

- [x] **06.01** Implementar o cadastro da sessão do debate e de seus participantes. Entregue na versão 0.5, com persistência por sessão e validação automatizada do cadastro.
- [ ] **06.02** Implementar reprodução de gravação como entrada de ensaio, preservando o ritmo e os horários.
- [ ] **06.03** Conectar a entrada de áudio ao vivo e permitir iniciar, pausar e encerrar a captura.
- [ ] **06.04** Segmentar o áudio e associar trechos à linha do tempo do evento, medindo atraso de entrada.
- [ ] **06.05** Integrar a transcrição contínua e distinguir resultados provisórios de trechos estabilizados.
- [ ] **06.06** Associar falas aos participantes, permitir correção manual e manter identificação indefinida quando houver dúvida.
- [ ] **06.07** Sinalizar dúvidas em números, nomes, negações, sobreposições e trechos inaudíveis, disponibilizando o áudio correspondente.
- [ ] **06.08** Versionar correções de transcrição e emitir o aviso para reprocessar as análises dependentes.
- [ ] **06.09** Tratar desconexões e retomadas, registrando lacunas e evitando duplicação silenciosa de trechos.

**Fase concluída quando:** Uma gravação e uma entrada ao vivo produzem transcrição rastreável, corrigível e com falhas visíveis.

## 07 Implementar a triagem de afirmações

**Responsável sugerido:** Equipe técnica e revisores. **Dependências:** 02, 05.

- [ ] **07.01** Detectar afirmações factuais e distinguir opiniões, promessas e enunciados sem definição suficiente.
- [ ] **07.02** Separar frases com várias afirmações, mantendo a ligação com a fala literal.
- [ ] **07.03** Extrair participante, tema, local, período, indicador e comparação sem preencher ambiguidades como fatos.
- [ ] **07.04** Preservar contexto suficiente para referências como nosso governo, aqui e no ano passado.
- [ ] **07.05** Priorizar as afirmações segundo os critérios editoriais e permitir intervenção humana. Parcial na versão 0.18: nível manual com justificativa e histórico; formalização e avaliação dos critérios editoriais pendentes.
- [ ] **07.06** Agrupar repetições equivalentes sem misturar períodos, territórios ou indicadores diferentes.
- [ ] **07.07** Permitir inclusão manual, edição, divisão e descarte com justificativa e histórico.
- [ ] **07.08** Medir precisão e cobertura contra a referência humana e registrar o que foi selecionado e descartado.

**Fase concluída quando:** Fila de afirmações utilizável com fidelidade à fala, prioridade explicável e resultados de avaliação registrados.

## 08 Implementar pesquisa e gestão de evidências

**Responsável sugerido:** Equipe técnica e revisores. **Dependências:** 02, 05.

- [ ] **08.01** Organizar uma coleção de fontes por tema, com instituição, metodologia, periodicidade e limites de uso.
- [ ] **08.02** Implementar busca na coleção preparada e na web, registrando as consultas realizadas. Parcial na versão 0.17: Tavily sob demanda com consultas e candidatas registradas; coleção preparada, chamada real e avaliação editorial pendentes.
- [ ] **08.03** Recuperar o conteúdo dos documentos e registrar bloqueio, indisponibilidade ou leitura incompleta.
- [ ] **08.04** Extrair trechos de páginas, PDFs e tabelas, guardando página, seção ou outro localizador verificável.
- [ ] **08.05** Registrar URL, autoria, data de publicação quando disponível, período dos dados, horário de acesso e versão do material.
- [ ] **08.06** Pesquisar evidências favoráveis, contrárias e contextualizadoras sem assumir uma classificação antecipadamente.
- [ ] **08.07** Relacionar documentos que reproduzem a mesma origem e explicitar a independência das evidências.
- [ ] **08.08** Localizar checagens anteriores e conferir equivalência da afirmação, validade temporal e diferenças de contexto antes de reutilizar.
- [ ] **08.09** Conferir se a informação já existia no momento da fala e registrar revisões posteriores separadamente.
- [ ] **08.10** Restringir a leitura de URLs a destinos permitidos e tratar instruções contidas nas páginas como conteúdo externo.

**Fase concluída quando:** Cada evidência aponta para conteúdo efetivamente recuperado e localizado, com origem, contexto e lacunas registrados.

## 09 Implementar análise e geração dos dossiês

**Responsável sugerido:** Equipe técnica e revisores. **Dependências:** 07, 08.

- [ ] **09.01** Relacionar cada afirmação às evidências recuperadas, distinguindo sustentação, contradição, contexto e insuficiência.
- [ ] **09.02** Conferir compatibilidade de período, território, população, indicador e metodologia.
- [ ] **09.03** Registrar cálculos reproduzíveis, unidades, bases de comparação e diferenças entre percentuais e pontos percentuais.
- [ ] **09.04** Gerar resumo fiel, síntese das evidências, classificação preliminar e justificativa.
- [ ] **09.05** Explicitar lacunas, conflitos entre fontes e perguntas que ainda precisam de pesquisa.
- [ ] **09.06** Conferir se as citações existem nos documentos e sustentam as conclusões associadas.
- [ ] **09.07** Gerar o dossiê no formato definido, com versões separadas para a análise automática e a decisão humana.
- [ ] **09.08** Encaminhar falhas de evidência e de consistência para correção, mantendo a análise pendente ou inconclusiva conforme o caso.

**Fase concluída quando:** Dossiê completo ou lacunas explícitas disponíveis, sem afirmações materiais sustentadas apenas pela resposta do modelo.

## 10 Coordenar os agentes e o processamento

**Responsável sugerido:** Equipe técnica. **Dependências:** 06, 07, 08, 09.

- [ ] **10.01** Implementar o coordenador que encaminha transcrição, triagem, pesquisa, análise e revisão de consistência.
- [ ] **10.02** Aplicar contratos de entrada e saída e registrar versões dos modelos, instruções e parâmetros.
- [ ] **10.03** Implementar fila por prioridade e limites de tarefas simultâneas por evento. A versão 0.18 ordena a visualização por prioridade manual; o escalonamento das tarefas por esse nível continua pendente.
- [ ] **10.04** Definir limites de duração, custo e tentativas por tarefa e por evento.
- [ ] **10.05** Permitir cancelar, repetir ou solicitar pesquisa adicional sem criar dossiês duplicados.
- [ ] **10.06** Impedir que resultados de uma versão antiga da fala sobrescrevam uma versão mais recente.
- [ ] **10.07** Invalidar análises dependentes quando a fala ou a evidência muda, preservando decisões anteriores no histórico.
- [ ] **10.08** Aplicar permissões que impeçam agentes de aprovar dossiês, alterar decisões humanas ou divulgar conteúdo.
- [ ] **10.09** Expor progresso, interrupções e atrasos ao painel, registrando os tempos de cada etapa.

**Fase concluída quando:** Fluxo integrado recuperável após falhas, com controle de versões, limites e decisão editorial restrita a pessoas autorizadas.

## 11 Construir o painel de revisão humana

**Responsável sugerido:** Produto, equipe técnica e revisores. **Dependências:** 03, 05, 10.

- [ ] **11.01** Exibir evento, participantes e transcrição com acesso ao trecho de áudio.
- [ ] **11.02** Exibir fila de afirmações com filtros por tema, participante, prioridade, estado e responsável. Parcial na versão 0.18: texto, escopo, categoria, tema, participante, estado e prioridade implementados; responsável pendente.
- [ ] **11.03** Permitir que um revisor assuma um caso e evitar sobrescrita entre revisões simultâneas.
- [ ] **11.04** Apresentar fala literal, contexto, pergunta de checagem e recortes definidos.
- [ ] **11.05** Exibir documentos, localizadores, evidências favoráveis e contrárias e lacunas de pesquisa.
- [ ] **11.06** Identificar a classificação da IA como preliminar e permitir examinar as evidências antes de consultá-la.
- [ ] **11.07** Permitir corrigir a afirmação, adicionar evidências, solicitar pesquisa, descartar ou concluir a revisão com justificativa.
- [ ] **11.08** Mostrar histórico e exigir nova validação quando o dossiê revisado mudar.
- [ ] **11.09** Implementar exportação interna com versão, responsável, fontes e estado de revisão, preservando a decisão de divulgação com o editor.
- [ ] **11.10** Verificar legibilidade, navegação por teclado e identificação de estados sem depender apenas de cores.

**Fase concluída quando:** Revisores conseguem executar o fluxo completo e consultar as fontes, com ações humanas registradas e permissões aplicadas.

## 12 Preparar monitoramento e operação

**Responsável sugerido:** Equipe técnica e operador. **Dependências:** 05, 10, 11.

- [ ] **12.01** Criar indicadores de latência por etapa, tamanho da fila, falhas, lacunas de áudio e uso dos serviços.
- [ ] **12.02** Apresentar custo acumulado e estimativa restante em relação ao orçamento do evento.
- [ ] **12.03** Configurar alertas para perda de áudio, atraso excessivo, falhas repetidas e aproximação dos limites.
- [ ] **12.04** Implementar os modos de operação previstos para falha de busca, transcrição ou modelo, mantendo pendências visíveis.
- [ ] **12.05** Definir acesso, retenção e exclusão de mídia, documentos, registros técnicos e dados dos usuários.
- [ ] **12.06** Testar cópia de segurança e recuperação dos registros do evento e das revisões.
- [ ] **12.07** Preparar ambiente de operação e procedimento de atualização e retorno à versão anterior.
- [ ] **12.08** Escrever instruções para iniciar, acompanhar, interromper e encerrar uma sessão e registrar incidentes.

**Fase concluída quando:** Operador consegue acompanhar qualidade, atrasos e custos e recuperar a operação conforme procedimentos documentados.

## 13 Validar o sistema em ensaio completo

**Responsável sugerido:** Equipe técnica, operador, revisores e editor. **Dependências:** 02, 06, 07, 08, 09, 10, 11, 12.

- [ ] **13.01** Testar o percurso de uma fala até a conclusão humana, incluindo pesquisa adicional e descarte.
- [ ] **13.02** Testar negações, números, nomes, falas sobrepostas, participante indefinido e correções de transcrição.
- [ ] **13.03** Testar comparação fora de contexto, fonte única, fontes conflitantes, conteúdo indisponível e checagem desatualizada.
- [ ] **13.04** Testar instruções maliciosas em documentos e bloqueio de URLs para destinos não permitidos.
- [ ] **13.05** Testar autorização, revisão simultânea e revalidação de dossiês alterados após aprovação.
- [ ] **13.06** Simular perda de áudio, falha de serviço, repetição de tarefas, excesso de afirmações e alcance dos limites de custo.
- [ ] **13.07** Executar o ensaio com gravação no ritmo original e participação da equipe humana.
- [ ] **13.08** Avaliar com o material reservado e comparar trabalho manual e assistido; incluir amostra revisada sem acesso prévio à sugestão da IA.
- [ ] **13.09** Corrigir falhas críticas, repetir os cenários afetados e registrar resultados e limitações da amostra.
- [ ] **13.10** Fixar limites de qualidade, latência e custo e conferir o desempenho antes de liberar o piloto ao vivo.

**Fase concluída quando:** Ensaio registrado, falhas críticas resolvidas e critérios operacionais atendidos para a versão que será usada no evento.

## 14 Preparar e executar o piloto ao vivo

**Responsável sugerido:** Editor, operador, revisores e equipe técnica. **Dependências:** 01, 13.

- [ ] **14.01** Confirmar evento, transmissão, participantes, horários e disponibilidade da equipe.
- [ ] **14.02** Preparar fontes por tema e revisar a validade das checagens que poderão ser reutilizadas.
- [ ] **14.03** Treinar a equipe no painel, nos estados do trabalho e nos procedimentos para falhas.
- [ ] **14.04** Conferir acesso ao áudio, autenticação, limites dos serviços, armazenamento e orçamento antes do evento.
- [ ] **14.05** Registrar a versão do sistema e a decisão de iniciar, adiar ou interromper conforme os critérios definidos.
- [ ] **14.06** Iniciar a sessão e acompanhar captura, transcrição, fila, pesquisas e distribuição dos casos.
- [ ] **14.07** Revisar os dossiês internamente, registrando correções, decisões, esperas e incidentes.
- [ ] **14.08** Controlar volume, atrasos e custos e acionar o procedimento de interrupção quando necessário.
- [ ] **14.09** Encerrar a sessão, identificar pendências e preservar os registros necessários à avaliação.

**Fase concluída quando:** Um debate político ao vivo acompanhado pela equipe, com registros completos das análises, decisões e condições de operação.

## 15 Avaliar o piloto e planejar a próxima versão

**Responsável sugerido:** Proponente, editor, revisores e equipe técnica. **Dependências:** 14.

- [ ] **15.01** Consolidar precisão, cobertura, correções, tempos, trabalho humano e custos, com os denominadores e pendências explícitos.
- [ ] **15.02** Avaliar fontes inventadas, atribuições incorretas, conclusões sem respaldo e falhas de autorização como incidentes específicos.
- [ ] **15.03** Examinar diferenças por participante, tema e complexidade à luz das afirmações elegíveis.
- [ ] **15.04** Coletar dificuldades dos revisores e comparar o esforço com a referência de trabalho manual.
- [ ] **15.05** Registrar o que funcionou, as limitações e as correções necessárias antes de repetir o piloto.
- [ ] **15.06** Decidir se o próximo ciclo será de correção, novo ensaio, novo debate ou ampliação de escopo.
- [ ] **15.07** Atualizar documentação e backlog e executar as regras de retenção ou exclusão do material do evento.

**Fase concluída quando:** Relatório de avaliação concluído e próximo ciclo definido com base em evidências do piloto.

## Marcos de acompanhamento

| Marco | Resultado esperado | Fases |
| --- | --- | --- |
| Especificação preparada | Piloto, metodologia, avaliação, telas, dados e tecnologias definidos. | 01 a 04 |
| Base técnica disponível | Ambiente, persistência, permissões e rastreabilidade funcionando. | 05 |
| Protótipo integrado | Áudio, afirmações, evidências, dossiês e revisão funcionando com monitoramento. | 06 a 12 |
| Pronto para o debate | Ensaio concluído e critérios de qualidade, latência e custo atendidos. | 13 |
| Piloto executado | Debate ao vivo acompanhado internamente e registros preservados. | 14 |
| Próximo ciclo definido | Resultado comparado com a referência humana e backlog atualizado. | 15 |

O primeiro bloco de trabalho é **01.01 a 01.04**: escolher o debate, confirmar o acesso à transmissão, designar a equipe e entender seu fluxo atual. Esses dados orientarão as decisões editoriais e técnicas seguintes.

## Documentação relacionada

- [Proposta inicial](proposta-inicial.md).
- [Operação e recuperação](operacao-e-recuperacao.md).
- [Diagramas de funcionamento](diagramas/README.md).
- [Índice do projeto](../README.md).
- [Checklist em página privada](https://chatgpt.com/space/page_ea170c8f1ddc8191885e9cf08919db22).

Os arquivos locais são a referência para evolução do projeto. A página de leitura e os arquivos deverão ser reconciliados quando houver alterações de conteúdo ou de andamento.
