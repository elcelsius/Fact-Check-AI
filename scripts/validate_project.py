"""Verificações locais usadas também pelo GitHub Actions, sem rede ou dados privados."""

from pathlib import Path
import re
import subprocess
import tomllib
import xml.etree.ElementTree as ET

from factcheck import __version__


def validate(root):
    root=Path(root).resolve()
    project=tomllib.loads((root/"pyproject.toml").read_text(encoding="utf8"))
    if project["project"]["version"]!=__version__:
        raise ValueError("A versão do pacote difere da versão do aplicativo.")
    count=0
    for path in [root/"README.md",*sorted((root/"docs").rglob("*.md"))]:
        for link in re.findall(r"\]\(([^)]+)\)",path.read_text(encoding="utf8")):
            if "://" in link or link.startswith("#"):
                continue
            target=(path.parent/link.split("#",1)[0]).resolve()
            if not target.is_relative_to(root) or not target.exists():
                raise ValueError(f"Link local inválido em {path.relative_to(root)}: {link}")
            count+=1
    for path in sorted((root/"docs/diagramas").glob("*.svg")):
        svg=ET.parse(path).getroot()
        if svg.tag!="{http://www.w3.org/2000/svg}svg" or __version__ not in path.read_text(encoding="utf8"):
            raise ValueError(f"Diagrama inválido ou com versão antiga: {path.name}")
        if svg.findall(".//{http://www.w3.org/2000/svg}script"):
            raise ValueError("Os diagramas SVG devem permanecer independentes e sem scripts.")
    plan=(root/"docs/checklist-desenvolvimento.md").read_text(encoding="utf8")
    tasks=re.findall(r"^- \[([ x])\] \*\*(\d\d\.\d\d)\*\*",plan,re.M)
    if len({task for _,task in tasks})!=len(tasks):
        raise ValueError("Há tarefas repetidas no checklist.")
    done=sum(mark=="x" for mark,_ in tasks)
    if f"{len(tasks)-done} tarefas pendentes e {done} entregas concluídas" not in plan:
        raise ValueError("As contagens do checklist não correspondem às caixas marcadas.")
    tracked=subprocess.run(["git","ls-files"],cwd=root,capture_output=True,text=True,check=True).stdout.splitlines()
    private={"recordings","library","models","exports","tmp","logs",".venv",".cache",".aws",".codex"}
    if any(path.split("/",1)[0] in private or path==".env" for path in tracked):
        raise ValueError("Há arquivos privados ou gerados no controle de versão.")
    return {"version":__version__,"local_links":count,"tasks":len(tasks),"completed":done,"pending":len(tasks)-done}


def main():
    print(validate(Path(__file__).resolve().parents[1]))


if __name__=="__main__":
    main()
