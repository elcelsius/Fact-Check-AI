"""Gera os dois diagramas SVG editáveis, sem dependências ou ativos externos.

Revisar os textos junto com a arquitetura quando o fluxo do produto mudar.
Executar da raiz: python -m scripts.generate_flow_diagrams
"""

from pathlib import Path
from xml.sax.saxutils import escape

from factcheck import __version__


PALETTE = {"blue": ("#EAF1FF", "#2455A4"), "teal": ("#E6F5F2", "#087F74"),
           "purple": ("#F0EDFF", "#6552B8"), "amber": ("#FFF3DE", "#9A5C00"),
           "gray": ("#F0F3F8", "#52637B")}


class Diagram:
    def __init__(self, width, height, title, description):
        self.width, self.height = width, height
        self.parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title description">',
                      f'<title id="title">{escape(title)}</title>', f'<desc id="description">{escape(description)}</desc>',
                      '''<defs>
  <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 Z" fill="#61738D"/></marker>
  <marker id="return" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 Z" fill="#B57A22"/></marker>
  <style>
    text { font-family: 'Segoe UI', Arial, sans-serif; fill: #23344E; }
    .title { font-size: 40px; font-weight: 700; letter-spacing: -.5px; }
    .subtitle { font-size: 19px; fill: #54667F; }
    .section { font-size: 14px; font-weight: 700; letter-spacing: 1.7px; fill: #60738D; }
    .heading { font-size: 21px; font-weight: 700; }
    .body { font-size: 17px; }
    .small { font-size: 15px; fill: #54667F; }
    .tag { font-size: 13px; font-weight: 700; letter-spacing: 1px; }
    .stage { font-size: 27px; font-weight: 700; }
    .number { font-size: 20px; font-weight: 700; fill: white; }
    .flow { fill: none; stroke: #61738D; stroke-width: 2.7; stroke-linejoin: round; marker-end: url(#arrow); }
    .return { fill: none; stroke: #B57A22; stroke-width: 2.2; stroke-linejoin: round; marker-end: url(#return); }
  </style>
</defs>''', f'<rect width="{width}" height="{height}" fill="#F5F7FC"/>']

    def rect(self, x, y, width, height, fill="white", stroke="#D8E1ED", radius=18, dashed=False):
        dash = ' stroke-dasharray="8 6"' if dashed else ''
        self.parts.append(f'<rect x="{x}" y="{y}" width="{width}" height="{height}" rx="{radius}" fill="{fill}" stroke="{stroke}" stroke-width="1.5"{dash}/>')

    def text(self, x, y, value, style="body", fill=None):
        color = f' style="fill:{fill}"' if fill else ''
        self.parts.append(f'<text x="{x}" y="{y}" class="{style}"{color}>{escape(value)}</text>')

    def lines(self, x, y, values, style="body", spacing=25):
        for index, value in enumerate(values):
            self.text(x, y + index * spacing, value, style)

    def path(self, value, style="flow"):
        self.parts.append(f'<path d="{value}" class="{style}"/>')

    def card(self, x, y, width, height, title, lines, color="blue", tag=None, planned=False):
        self.parts.append(f'<g data-card-bounds="{x},{y},{width},{height}">')
        light, dark = PALETTE[color]
        self.rect(x, y, width, height, "white", "#A9B5C6" if planned else "#D8E1ED", dashed=planned)
        self.parts.append(f'<path d="M {x+18} {y} H {x+width-18} Q {x+width} {y} {x+width} {y+18} V {y+10} H {x} V {y+18} Q {x} {y} {x+18} {y} Z" fill="{dark}"/>')
        if tag:
            self.rect(x+18, y+20, width-36, 26, light, light, 7)
            self.text(x+28, y+38, tag, "tag", dark)
        heading_y = y+76 if tag else y+39
        self.text(x+20, heading_y, title, "heading")
        self.lines(x+20, heading_y+31, lines, spacing=25)
        self.parts.append('</g>')

    def header(self, eyebrow, title, subtitle):
        self.text(60, 45, eyebrow, "section")
        self.text(60, 96, title, "title")
        self.text(60, 133, subtitle, "subtitle")

    def save(self, path):
        path.write_text("\n".join([*self.parts, "</svg>"]) + "\n", encoding="utf8", newline="\n")


def internal(path):
    svg = Diagram(1600, 1550, "Fact-Check AI — funcionamento interno",
                  "Fluxo atual do áudio aos dossiês: captura, transcrição local, triagem, validação, fila, planejamento, fontes, análise opcional e decisão humana. Funções futuras aparecem em caixas tracejadas.")
    svg.header(f"FACT-CHECK AI / ARQUITETURA / REFERÊNCIA {__version__}", "Como o sistema processa uma fala",
               "Filas independentes, registros versionados e decisão factual sob responsabilidade humana.")
    svg.text(60, 187, "01 / ÁUDIO E TRANSCRIÇÃO LOCAL", "section")
    xs, width = [60, 450, 840, 1230], 310
    row1 = [
        ("Vídeo no navegador", ["YouTube, Globoplay, Band…", "A aplicação capta a saída", "usada para ouvir o vídeo."], "gray", "ENTRADA"),
        ("Captura da saída", ["WASAPI loopback · PCM16", "Fila de captura separada", "WAV salvo durante a sessão."], "blue", "CAPTURA"),
        ("Transcrição local", ["sherpa-onnx ou Whisper", "Hipóteses provisórias", "Só trechos estáveis persistem."], "blue", "PROCESSO LOCAL"),
        ("Parágrafos", ["Pausas e continuidade", "Ligação aos trechos originais", "Tempos relativos à captura."], "teal", "ORGANIZAÇÃO")]
    for x, (title, lines, color, tag) in zip(xs, row1):
        svg.card(x, 210, width, 187, title, lines, color, tag)
    for x in xs[:-1]:
        svg.path(f"M {x+width} 304 H {x+390}")
    svg.text(60, 435, "Pacotes curtos alimentam o reconhecimento; tamanho do pacote não equivale à latência de uma palavra.", "small")
    svg.text(60, 492, "02 / EXTRAÇÃO, VALIDAÇÃO E REVISÃO", "section")
    row2 = [
        ("Revisão do operador", ["Conferir fala e participante", "Editar / reclassificar extração", "Combinar trechos com histórico."], "amber", "AÇÃO HUMANA"),
        ("Fila de afirmações", ["Fatos, opiniões e promessas", "Prioridade, responsável e filtros", "Estados atuais e históricos."], "teal", "INTERFACE"),
        ("Validar extrações", ["Citação ligada ao texto", "Controles de número e negação", "Resposta inválida é rejeitada."], "teal", "CONTROLES"),
        ("Triagem de afirmações", ["Qwen local OU Gemini opcional", "Tarefa em processo separado", "Não decide a veracidade."], "purple", "IA / FILA DE TAREFAS")]
    for x, (title, lines, color, tag) in zip(xs, row2):
        svg.card(x, 515, width, 187, title, lines, color, tag)
    svg.path("M 1385 397 V 515")
    for x in reversed(xs[1:]):
        svg.path(f"M {x} 609 H {x-80}")
    svg.text(765, 590, "válidas", "small")
    svg.text(450, 743, "Se corrigir a transcrição, solicite nova triagem. Revisar uma extração não inicia inferência.", "small")
    svg.text(450, 800, "03 / PESQUISA ASSISTIDA E DECISÃO", "section")
    row3 = [
        ("Planejar checagem", ["Pergunta, recortes e lacunas", "Rascunho de IA identificado", "URLs candidatas ≠ evidências."], "amber", "PERGUNTA E CONTEXTO"),
        ("Descobrir e coletar", ["Coleção local ou Tavily opcional", "Coleta por URL ou PDF/HTML", "Candidatas ≠ evidências coletadas."], "teal", "BUSCA / COLETA / IMPORTAÇÃO"),
        ("Análise preliminar", ["Gemini opcional e explícito", "Somente evidências fornecidas", "Lacunas → resultado inconclusivo."], "purple", "IA / NÃO APROVADA"),
        ("Decisão humana", ["Conferir fontes e recortes", "Confirmada / contradita /", "inconclusiva + justificativa."], "amber", "REVISOR RESPONSÁVEL")]
    for x, (title, lines, color, tag) in zip(xs, row3):
        svg.card(x, 823, width, 187, title, lines, color, tag)
    svg.path("M 215 702 V 823")
    for x in xs[:-1]:
        svg.path(f"M {x+width} 917 H {x+390}")
    svg.text(845, 1048, "Sem API: leitura e decisão humanas continuam disponíveis.", "small")
    svg.card(60, 1112, 680, 174, "Persistência por sessão", ["audio.wav + transcrição / parágrafos JSONL e TXT", "SQLite: revisões, buscas, fontes e dossiês", "Originais e histórico preservados; recuperação após interrupção."], "blue", "ARQUIVOS + BANCO LOCAL")
    svg.card(770, 1112, 350, 174, "Controle transversal", ["Versões e resultados antigos", "Cancelamento com confirmação", "Chaves de API só na memória."], "gray", "COORDENADORES E FILAS")
    svg.card(1230, 1112, 310, 174, "Exportação interna", ["Sessão JSON / tabelas CSV", "Dossiê e relatório do ensaio", "Pendências acompanham o arquivo."], "teal", "SEM PUBLICAÇÃO AUTOMÁTICA")
    svg.path("M 1385 1010 V 1112")
    svg.path("M 605 397 V 411 H 32 V 1199 H 60")
    svg.text(42, 1090, "WAV", "small")
    svg.text(60, 1336, "COLEÇÃO ENTRE SESSÕES", "section")
    svg.text(545, 1336, "EVOLUÇÃO PLANEJADA / CAIXAS TRACEJADAS", "section")
    svg.card(60, 1360, 450, 118, "Coleção de fontes", ["library/sources.sqlite3 · metadados", "Versão copiada para o caso selecionado."], "teal")
    svg.path("M 510 1419 H 525 V 1307 H 750 V 1080 H 605 V 1010")
    svg.card(545, 1360, 450, 118, "Pesquisa e falantes", ["Busca contínua e checagens anteriores.", "Separação automática de falantes."], "gray", planned=True)
    svg.card(1030, 1360, 510, 118, "Operação em equipe", ["Contas, permissões e sincronização.", "Distribuição entre operadores."], "gray", planned=True)
    svg.text(60, 1520, "Setas: percurso principal possível. A coleta e a exportação não exigem aprovação factual; a divulgação depende da equipe editorial.", "small")
    svg.save(path)


def user(path):
    svg = Diagram(1440, 1570, "Fact-Check AI — jornada do usuário",
                  "Jornada em quatro etapas: preparar e capturar, conferir e organizar, pesquisar evidências, decidir e exportar. Correções e encerramento têm proteção; funcionalidades futuras aparecem tracejadas.")
    svg.header(f"FACT-CHECK AI / JORNADA DO USUÁRIO / REFERÊNCIA {__version__}", "Da transmissão ao dossiê revisado",
               "Você acompanha e decide. A IA ajuda a localizar afirmações e organizar a pesquisa.")
    svg.rect(60, 165, 1320, 57, "#E6F5F2", "#B5DCD4", 12)
    svg.text(82, 201, "Conferir transcrição, revisar extração e decidir fatos são três atividades diferentes.", "body", "#087F74")

    def stage(x, y, number, title, actions, outcome, color):
        svg.parts.append(f'<g data-card-bounds="{x},{y},620,340">')
        light, dark = PALETTE[color]
        svg.rect(x, y, 620, 340)
        svg.parts.append(f'<circle cx="{x+40}" cy="{y+42}" r="22" fill="{dark}"/>')
        svg.text(x+34, y+49, str(number), "number")
        svg.text(x+78, y+51, title, "stage")
        svg.lines(x+25, y+101, actions, spacing=31)
        svg.rect(x+20, y+244, 580, 75, light, light, 11)
        svg.lines(x+35, y+273, outcome, spacing=25)
        svg.parts.append('</g>')

    stage(60, 260, 1, "Preparar e capturar", ["• Cadastre o debate e prepare a coleção de fontes.", "• Reproduza o vídeo e escolha a saída de áudio.", "• Use IA local ou configure sua chave Gemini.", "• Inicie a captura e informe a minutagem do vídeo."],
          ["O aplicativo grava áudio e mostra texto provisório.", "Parágrafos concluídos podem alimentar a triagem."], "blue")
    stage(760, 260, 2, "Conferir e organizar", ["• Encerre e salve para ouvir os trechos gravados.", "• Corrija a fala e atribua o participante.", "• Confira categoria, resumo e citação da extração.", "• Defina prioridade e responsável; use os filtros."],
          ["Fatos, opiniões e promessas têm estados próprios.", "A revisão da extração não aprova a afirmação."], "amber")
    stage(760, 740, 3, "Pesquisar evidências", ["• Defina pergunta, recortes e lacunas no dossiê.", "• Use a coleção, Tavily ou o navegador.", "• Colete a URL ou importe PDF/HTML e confira.", "• Opcional: peça análise preliminar ao Gemini."],
          ["URLs candidatas ficam separadas das evidências.", "Contexto insuficiente pede nova conferência."], "purple")
    stage(60, 740, 4, "Decidir e exportar", ["• Leia as fontes e confronte dados e contexto.", "• Registre a decisão humana com justificativa:", "  confirmada, contradita ou inconclusiva.", "• Exporte o dossiê, os dados e o relatório do ensaio."],
          ["Arquivos podem conter pendências identificadas.", "A publicação permanece com a equipe editorial."], "teal")
    svg.path("M 680 430 H 760")
    svg.path("M 1070 600 V 740")
    svg.path("M 760 910 H 680")
    svg.path("M 1270 740 V 645 H 1250 V 600", "return")
    svg.lines(1095, 653, ["Falta contexto?", "Confira a fala."], "small", spacing=23)
    svg.text(60, 1140, "AÇÕES DE APOIO DURANTE O TRABALHO", "section")
    svg.card(60, 1166, 410, 210, "Se houver uma correção", ["O histórico permanece disponível.", "Resultados anteriores são invalidados.", "O plano pode pedir nova conferência.", "Uma tarefa antiga não substitui a edição."], "amber", "REVISÕES PROTEGIDAS")
    svg.card(515, 1166, 410, 210, "Ao cancelar ou fechar", ["Uma atividade em andamento pede", "confirmação de cancelamento.", "Dados já salvos são preservados.", "Texto provisório pode ser perdido."], "blue", "ENCERRAMENTO E RECUPERAÇÃO")
    svg.card(970, 1166, 410, 210, "Ainda planejado", ["Pesquisa contínua e checagens anteriores", "Separação automática de falantes", "Contas e operação em equipe"], "gray", "EVOLUÇÃO DO PROTÓTIPO", planned=True)
    svg.rect(60, 1420, 1320, 80, "#EAF1FF", "#CEDCF5", 12)
    svg.lines(83, 1452, ["Para começar: faça um ensaio curto e confira um caso completo antes de acompanhar um evento ao vivo.",
                       "A análise da IA é preliminar. A validação e qualquer divulgação continuam sob responsabilidade humana."], spacing=25)
    svg.text(60, 1540, "Fluxo recomendado para revisão. Captura, triagem e pesquisa podem ocorrer em paralelo, respeitando os estados e as tarefas ativas.", "small")
    svg.save(path)


def main():
    folder = Path(__file__).resolve().parents[1] / "docs" / "diagramas"
    folder.mkdir(parents=True, exist_ok=True)
    internal(folder / "fluxo-interno.svg")
    user(folder / "fluxo-usuario.svg")
    print("Diagramas SVG gravados em docs/diagramas.")


if __name__ == "__main__":
    main()
