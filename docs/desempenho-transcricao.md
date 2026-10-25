# Comparação e desempenho da transcrição

**Versão 0.24.0 · 24/10/2026 · ensaios locais**

O objetivo deste incremento é medir os dois motores com o mesmo áudio e reduzir o acúmulo de fila. A versão 0.24 acrescenta Whisper com NVIDIA, preparação dos kernels antes de gravar e comparação automática em processos separados. A seleção inicial continua sendo o motor contínuo em CPU; o operador escolhe a alternativa NVIDIA explicitamente. Todos os caminhos de transcrição permanecem locais.

## Como usar no aplicativo

1. Abra **iniciar.cmd** e escolha **Whisper · NVIDIA (GPU) · trechos a cada três segundos** em **Transcrição**. As bibliotecas opcionais já foram preparadas neste computador.
2. Para uma instalação nova com GPU NVIDIA compatível, instale o [requirements-gpu.lock](../requirements-gpu.lock) dentro da venv. Esse arquivo reúne o backend da triagem e os runtimes CUDA 12 necessários ao Whisper; os runtimes CUDA 13 da triagem continuam presentes. Não instala drivers, altera o toolkit global ou configura o PATH do Windows. As bibliotecas CUDA 12 adicionais representam aproximadamente 1,4 GB de download.
3. Use **Ensaiar WAV salvo** ou **Iniciar captura**. Aguarde a mensagem de captura iniciada antes de reproduzir o trecho que deseja gravar. A preparação NVIDIA pode levar dezenas de segundos; ela acontece antes de abrir a entrada e usa somente uma amostra sintética descartada.
4. Confira os trechos estabilizados. O modo Whisper trabalha em janelas: não fornece a prévia revisável do motor contínuo. O primeiro envio ocorre após dois segundos, depois a cada três segundos, com até seis segundos de contexto e meio segundo de margem à direita.

Sem runtime ou GPU compatível, a opção NVIDIA falha com diagnóstico; não muda silenciosamente o processador. Escolha **Whisper · CPU** ou o modo contínuo para continuar. Cancelar ou fechar durante a preparação exige confirmação e pode aguardar uma chamada nativa em andamento. O áudio e a conferência humana mantêm os controles existentes.

Na linha de comando:

```powershell
.\.venv\Scripts\python.exe -m factcheck --engine whisper --whisper-device cuda --prepare-model
.\.venv\Scripts\python.exe -m factcheck --engine whisper --whisper-device cuda --replay-wav recordings\PASTA_DA_SESSAO\audio.wav
```

## Comparação reproduzível

Prepare previamente os modelos que pretende medir. A comparação não baixa modelos, abre dispositivo, toca áudio, chama APIs ou inicia triagem e pesquisa. Cada perfil passa pela captura WAV real do aplicativo, no ritmo original, em processo Windows próprio. Os ensaios são sequenciais; nas repetições seguintes, a ordem é invertida para tornar explícito o efeito da ordem.

```powershell
.\.venv\Scripts\python.exe -m scripts.compare_transcription recordings\PASTA_DA_SESSAO\audio.wav --profiles streaming-cpu whisper-cpu whisper-cuda --repeats 1
```

Sem `--profiles`, são comparados somente os dois perfis CPU. Use `--profiles whisper-cuda` para um ensaio longo isolado. `--whisper-model small` é o padrão; tiny e base exigem preparo prévio e outra avaliação de fidelidade. `--repeats` aceita de uma a cinco execuções por perfil. `--output caminho.json` escolhe o relatório; um JSON de outro tipo não é sobrescrito.

O resultado padrão fica em `.cache/verification/asr-comparison-<horário UTC>.json`. Ele contém transcrições automáticas e caminhos locais e deve permanecer privado. Cada execução cria uma sessão em `recordings`, que pode ser aberta no aplicativo para ouvir e revisar o texto. O cadastro dessas sessões é de ensaio, sem validação do evento ou dos participantes. Os originais permanecem intactos; SHA-256 do arquivo e do PCM verificam a entrada e a cópia. Os hashes dos modelos registram a configuração medida. Alterações no áudio ou nos modelos interrompem a comparação.

O JSON distingue:

| Medida | O que significa |
| --- | --- |
| Preparação e setup | Carregamento, aquecimento e abertura da sessão; excluídos das latências desde a entrada de áudio. |
| Primeira prévia | Primeira hipótese provisória do contínuo; ausente no Whisper, sem ser convertida em zero. |
| Primeiro texto estabilizado | Primeira entrega persistida do motor; continua pendente de revisão humana. |
| Inferência / duração do áudio | Computação dos trechos e flush do contínuo, sem escrita dos resultados. Valor abaixo de um é condição útil, mas não garante estabilidade em outra carga. |
| Processamento do trecho | Inclui inferência e persistência; separado da computação do motor. |
| Atraso de entrega | Tempo entre a posição de áudio e sua entrega; não equivale à latência de uma palavra individual. |
| Fila máxima registrada | Maior quantidade observada nos eventos, sem afirmar medir toda mudança instantânea da fila. |
| Drenagem após captura | Trabalho restante entre encerrar a entrada e finalizar a sessão; exclui a preparação inicial. |

O P95 exige pelo menos vinte observações. Medidas antigas ausentes permanecem nulas. O relatório do ensaio disponível pela interface também identifica CPU/NVIDIA e separa inferência, processamento e flush nas novas sessões. Os formatos anteriores continuam legíveis.

## Ensaios no computador de desenvolvimento

Foram usados somente WAVs já existentes, sem nova captura do sistema, APIs ou inferência de veracidade. O computador possui i9-14900HX e RTX 5060 Laptop de 8 GB; os testes usaram sherpa-onnx 1.13.8, faster-whisper 1.2.1 e CTranslate2 4.8.3. O driver observado foi 621.01. A carga de outros programas, energia e caches não foram controlados; as medidas não são promessa para outros computadores.

A rodada inicial de CPU levou aproximadamente 39,1 s no contínuo e 41,2 s no Whisper small para processar trechos de 20,011 s. São medidas do pipeline, sem o flush final do contínuo, registradas antes da separação da inferência neste incremento. Diminuir threads do Whisper de oito para quatro não resolveu o gargalo e não foi aplicado como ajuste padrão.

O teste NVIDIA curto, já com aquecimento antes da captura, processou o mesmo áudio em 12,99 s de inferência: razão 0,65. A primeira entrega estabilizada ocorreu em 3,41 s; a fila máxima registrada foi dois trechos e a drenagem final, 2,92 s. A preparação levou 68,07 s nessa execução. A mudança antecipou o custo inicial dos kernels para a preparação e reduziu a computação durante a entrada.

Na gravação de **336,341 s**, a inferência NVIDIA consumiu **225,68 s**, razão **0,67**. A primeira entrega ocorreu em **3,09 s**, a fila máxima registrada foi **cinco trechos** e a drenagem final, **1,80 s**. A preparação levou **35,67 s**. A entrega dos segmentos teve mediana **3,51 s**, P95 **16,51 s** e máximo **19,43 s**. O maior atraso de pacote foi **17,15 s**. Houve picos, com recuperação posterior da fila; não houve perda do PCM ou aviso de falha, e a transcrição foi integralmente finalizada.

Esses dois ensaios ocorreram durante o desenvolvimento da 0.24, antes da atualização do identificador da versão. Os relatórios originais, áudios e transcrições ficam locais e não são alterados para apresentar uma medição diferente.

A rodada seguinte usou a ferramenta de comparação já identificada como **0.24.0**, os três perfis em processos separados e o mesmo WAV de **20,011 s**. O relatório `.cache/verification/asr-three-profiles-v024.json` confirmou entrada, cópias PCM e modelos intactos; as três transcrições terminaram sem falhas:

| Perfil | Inferência, incluindo flush | Razão inferência/áudio | Primeiro texto estabilizado | Fila máxima registrada | Drenagem final |
| --- | --- | --- | --- | --- | --- |
| Contínuo CPU | 40,03 s | 2,00 | 5,48 s | 50 | 21,09 s |
| Whisper small CPU | 40,61 s | 2,03 | 7,09 s | 5 | 22,66 s |
| Whisper small NVIDIA | 12,88 s | 0,64 | 3,37 s | 2 | 2,72 s |

A preparação e abertura levaram 1,66 s, 1,12 s e 32,81 s, respectivamente, fora das medidas desde a entrada do áudio. Somente o contínuo produziu prévia provisória, em 2,22 s. Os atrasos máximos de pacote foram 19,12 s, 22,73 s e 2,81 s. A quantidade de itens na fila não compara diretamente os motores: o contínuo usa pacotes de 0,2 s e Whisper usa janelas sobrepostas com atualização de 3 s; os registros finais também podem incluir o marcador de encerramento.

Nessa rodada, a computação NVIDIA foi cerca de três vezes mais rápida que os dois perfis CPU. A preparação inicial permanece relevante e os picos do ensaio longo precisam de acompanhamento. Nenhum resultado determina qual transcrição é mais fiel sem ouvir o áudio e preparar a referência humana.

A suíte local passou com **529 testes em 178,992 s**. A interface NVIDIA foi inspecionada em 1120×860 e 1000×760; os dois diagramas foram renderizados sem cortes. Os testes automatizados de CUDA usam modelos e bibliotecas simulados; a execução NVIDIA real é demonstrada pelos ensaios acima. O ambiente passou por `pip check`. A [verificação automática](../.github/workflows/tests.yml) usa o backend CPU em Windows, sem baixar modelos ou usar chaves.

## Conferência humana e próximo ensaio

Velocidade não mede fidelidade: erro por palavra, nomes, números, negações e atribuição de participantes continuam sem referência humana. Os testes não rodaram a triagem Qwen simultaneamente; dividir GPU com outras tarefas pode alterar tempos e memória disponível. A opção NVIDIA melhora a capacidade neste ensaio, mas os picos observados ainda impedem prometer latência curta constante.

Abra uma sessão de ensaio no aplicativo, ouça os mesmos intervalos no original e confira os textos de cada motor. Anote omissões e acréscimos, nomes, números e qualificadores, preservando falante desconhecido quando houver dúvida. Escolha uma afirmação factual, ajuste os dados da transmissão para o evento real e complete um dossiê com recortes, evidências e decisão humana. Exporte e reabra os arquivos para conferir a proveniência e as pendências. A [metodologia editorial](metodologia-editorial.md) e o [guia operacional](operacao-e-recuperacao.md) orientam esse percurso.

Referências de implementação: [faster-whisper e requisitos GPU](https://github.com/SYSTRAN/faster-whisper#gpu), [CTranslate2](https://opennmt.net/CTranslate2/installation.html) e [instalação cuDNN Windows por pip](https://docs.nvidia.com/deeplearning/cudnn/installation/latest/windows.html#python-wheels-windows-installation). Os runtimes da venv são fixados no lockfile; a presença de um driver NVIDIA, por si só, não confirma todas as bibliotecas ou o desempenho.
