# Diagramas de funcionamento

Referência do protótipo **0.18.0**, de 23/10/2026. Os arquivos são SVGs independentes, com texto selecionável, título e descrição de acessibilidade, sem imagens ou fontes externas.

| Arquivo | Leitura |
| --- | --- |
| [Fluxo interno](fluxo-interno.svg) | Acompanha áudio, transcrição, triagem, validação, revisão, planejamento, evidências e conclusão. Destaca arquivos por sessão e controles de versão e cancelamento. |
| [Jornada do usuário](fluxo-usuario.svg) | Organiza o uso em quatro etapas: preparar e capturar; conferir e organizar; pesquisar evidências; decidir e exportar. Inclui o retorno à fala quando falta contexto. |

Setas mostram um percurso principal possível. Captura, triagem e pesquisa têm tarefas próprias e podem se sobrepor; os controles de versão impedem que resultados antigos substituam uma edição. Nem a coleta nem a exportação interna exigem uma conclusão factual. Os estados pendentes acompanham os arquivos.

Azul representa processamento local; verde, organização e evidências; roxo, tarefas de IA; amarelo, ações humanas. Os títulos também identificam essas funções. Caixas tracejadas descrevem somente evolução planejada: pesquisa contínua e reutilização de checagens, separação de falantes e distribuição de casos com responsáveis. Hoje, o participante é atribuído manualmente. A fila já oferece prioridade manual com justificativa e conferência após alterações da extração; ela organiza a visualização, sem mudar o veredito ou as tarefas em execução. A Tavily opcional encontra URLs por consulta solicitada pelo operador; selecionar e coletar documentos continua sendo uma ação humana. Gemini também é opcional. A transcrição local, a busca no navegador e a conferência humana funcionam sem essas APIs.

Transcrição estabilizada, extração revisada, análise preliminar e decisão humana são estados diferentes. Nenhuma etapa publica resultados automaticamente. O piloto editorial e a avaliação com referência humana continuam pendentes.

Para abrir, arraste um SVG para o navegador. Para editar, use um editor vetorial ou altere o gerador e regenere os dois arquivos, na raiz do projeto:

```powershell
.\.venv\Scripts\python.exe -m scripts.generate_flow_diagrams
```

O gerador usa a biblioteca padrão e a versão de `factcheck.__version__`. Seu código está em [scripts/generate_flow_diagrams.py](../../scripts/generate_flow_diagrams.py). Ele substitui somente os dois SVGs desta pasta; registre novas mudanças de fluxo também no [README](../../README.md) e no [checklist](../checklist-desenvolvimento.md).
