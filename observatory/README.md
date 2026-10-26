# observatory/

O código que serve as medições — a API HTTP, o coletor e o emissor — não é
publicado neste repositório.

Razão: os payloads e os arquivos de resultado do observatório carregam
endereço, S_RAW e PnL adiante por agente, e dado on-chain não se anonimiza
por hash: as operações são re-identificáveis pelos timestamps. Publicar o
código de serviço ao lado do universo que ele atende aproxima a reprodução
da re-identificação.

O que é publicado, e é o que a canonicidade exige:

- `scorer/` — o scorer versionado, que transforma entrada em S_RAW e SISTEMA
- `docs/SPEC_CHANGE_*.md` — cada mudança de especificação, com efeito medido
- `docs/D*.md` — os achados e as regras adotadas
- `docs/evidence/` — os scripts de evidência e os agregados
- os manifestos de hash das entradas de cada medição

Uma cópia de `scores_api.py` esteve rastreada aqui entre 2026-10-07 e
2026-10-26. Ela parou em 7 de outubro, com 296 linhas contra as 825 da
versão em serviço, e não continha a regra D12. Foi removida por descrever
um sistema que não existia, e não é reposta pela razão acima.
