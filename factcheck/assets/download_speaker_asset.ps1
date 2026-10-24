param(
    [Parameter(Mandatory=$true)] [ValidateSet('197666131','198893098')] [string] $AssetId,
    [Parameter(Mandatory=$true)] [string] $Destination
)
$ErrorActionPreference = 'Stop'
# O chamador fornece um temporário próprio. Não executar comandos do conteúdo baixado.
Invoke-WebRequest -UseBasicParsing -Uri ('https://api.github.com/repos/k2-fsa/sherpa-onnx/releases/assets/' + $AssetId) `
    -Headers @{Accept='application/octet-stream'; 'User-Agent'='Fact-Check-AI-model-preparation'} `
    -OutFile $Destination
