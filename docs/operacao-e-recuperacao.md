# Operação e recuperação de uma sessão

Procedimento do protótipo Windows, versão **0.12.0**, de 23/10/2026. As funções são locais; nenhuma pesquisa ou chamada à IA é retomada automaticamente ao abrir uma sessão.

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
