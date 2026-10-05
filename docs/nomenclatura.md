# Nomenclatura

> **Decidido com a TREELE em 17/09/2026.** O sistema já está configurado com o
> padrão abaixo. Este documento passa a ser a referência da equipe.

## Por que isso é o item mais importante do sistema

O nome do arquivo não é rótulo: é **o cadastro**. Quando alguém sobe
`TRL001-ARQ-PE-001-R02.pdf`, o sistema lê dali a obra, a disciplina, a fase, o
documento e a revisão, e arquiva sozinho. Ninguém preenche formulário, então
ninguém erra o preenchimento.

É por isso que arquivo fora do padrão é **recusado**, não aceito com aviso. Um
arquivo que o sistema não sabe classificar é exatamente o arquivo que some.

## O padrão da TREELE

```
OBRA-DISCIPLINA-FASE-PRANCHA-REVISÃO
```

No template do sistema:

```
{obra}-{disciplina}-{fase}-{prancha}-R{revisao}
```

Exemplo: `TRL001-ARQ-PE-001-R00.pdf`

| Campo | Tipo | Regra | Exemplos |
|---|---|---|---|
| `obra` | obra | Precisa ser o código da obra de destino | `TRL001` |
| `disciplina` | disciplina | Precisa existir no cadastro | `ARQ`, `EST`, `FUN` |
| `fase` | fase | Precisa existir no cadastro | `PE`, `PB`, `AP` |
| `prancha` | código livre | **Formato livre.** Letras, números, ponto, hífen e underscore | `001`, `PAV1`, `01.A`, `T-04` |
| `revisao` | revisão | Sempre `R` + 2 dígitos | `R00`, `R01`, `R12` |

Formatos aceitos: `.dwg`, `.rvt`, `.pdf`, `.ifc`.

Maiúsculas e minúsculas não importam no envio — o sistema normaliza tudo para
maiúsculas. `trl001-arq-pe-001-r00.pdf` e `TRL001-ARQ-PE-001-R00.PDF` são o
mesmo arquivo.

### Sobre o número da prancha ser livre

Vocês numeram prancha de formas diferentes conforme a obra, então esse campo não
impõe formato. Aceita `001`, `1`, `PAV1`, `01.A`, `T-04`, `CORTE.AA`.

Ele **aceita hífen**, apesar de o hífen ser o separador do padrão. Funciona
porque obra, disciplina e fase nunca têm hífen, e a revisão fica ancorada no fim
do nome: em `TRL001-EST-PE-T-04-R07.dwg` o sistema identifica corretamente a
prancha `T-04` e a revisão `07`.

A única coisa recusada é **barra** (`/` ou `\`), porque viraria subpasta no
armazenamento.

### Como o código do documento é formado

O **código do documento** é a junção de obra, disciplina, fase e prancha — tudo
menos a revisão:

```
TRL001-ARQ-PE-001-R00.pdf  →  documento TRL001-ARQ-PE-001, revisão 00
TRL001-ARQ-PE-001-R01.pdf  →  documento TRL001-ARQ-PE-001, revisão 01
```

As duas linhas acima são o **mesmo documento** em revisões diferentes. É isso que
monta o histórico automaticamente.

## Título: preenchido na interface, não no nome do arquivo

Por decisão de vocês, o título descritivo ("Planta de Forma — Pav. Tipo") fica
**fora** do nome do arquivo. O nome carrega só identificação.

**O título é obrigatório no primeiro envio do documento** (decisão de 25/09/2026).
Ao enviar a primeira revisão de uma prancha nova, a tela de envio pede o título
antes de liberar o botão — um campo por documento, mesmo que suba PDF e DWG
juntos. Ele é do documento, não da revisão: nas revisões seguintes é
reaproveitado, e ninguém digita de novo.

A regra mora no servidor, não só na tela: um envio sem título para documento
novo é recusado antes de criar qualquer coisa.

Documento que ficou sem título (de antes da regra) pede um no próximo envio.
Trocar o título depois se faz na tela do documento, em **Editar título**, por
quem pode enviar; apagar, não — todo documento tem título.

Na lista e na pasta, o título é a linha em destaque: ninguém procura
"MIL-ELE-PE-001", procura "Pontos Elétricos Pav. Tipo".

## Catálogos

### Disciplinas (26)

| | | |
|---|---|---|
| `ARQ` Arquitetura | `EST` Estrutura | `FUN` Fundação |
| `CON` Contenção | `ESC` Escoramento | `MUR` Muros |
| `PAT` Patamarização | `COB` Cobertura | `ESQ` Esquadria |
| `IMP` Impermeabilização | `HID` Hidrossanitário | `DRE` Drenagem |
| `ELE` Elétrica | `INC` Incêndio | `CLI` Climatização |
| `TEL` Telecomunicações | `GAS` Gás | `AUT` Automação |
| `TOP` Topografia | `TER` Terraplenagem | `PAV` Pavimentação |
| `URB` Implantação e Urbanismo | `PAI` Paisagismo | `INT` Interiores |
| `COO` Coordenação e Compatibilização | `COM` Comercial | |

As nove confirmadas por vocês em 17/09/2026 — COB, CON, DRE, ESC, ESQ, FUN,
IMP, MUR e PAT — já estão cadastradas. `COM` (Comercial) entrou em 02/10/2026,
a pedido da TREELE: é a única disciplina que o perfil comercial enxerga.
`INC` (Incêndio) entrou em 05/10/2026, também a pedido da TREELE, no lugar do
`PCI` (Prevenção e Combate a Incêndio) da proposta inicial — que foi
**desativado** e não aceita arquivo novo. Nenhum documento usava `PCI`.

> **Falta confirmar:** as outras 15 vieram da minha proposta inicial. Se alguma
> tiver código diferente do que vocês usam (por exemplo, se vocês chamam
> climatização de `AVA` em vez de `CLI`), me diga que eu ajusto. Disciplina
> desativada não aceita envios novos, mas o acervo já existente continua válido.

### Fases (7)

Em ordem cronológica de projeto, que é a ordem em que aparecem nos filtros:

`EP` Estudo Preliminar · `AP` Ante-projeto · `PL` Projeto Legal ·
`PA` Projeto Aprovado · `PB` Projeto Básico · `PE` Projeto Executivo ·
`AB` As-Built

`LV` (Levantamento) e `EV` (Estudo de Viabilidade) vieram da proposta inicial e
foram **desativados** em 17/09/2026 — não aceitam arquivo novo, mas nunca foram
apagados: documento antigo que aponte para eles continua válido e acessível.

## Regra de arquivo companheiro

Configurada por obra, verificada **na hora de liberar para obra** (não no envio):

- DWG não é liberado sem o PDF plotado na mesma revisão.
- RVT não é liberado sem o IFC exportado na mesma revisão.

Não é burocracia. São duas garantias:

1. **Quem está em campo sempre tem um formato que abre em qualquer lugar** — o
   PDF. Ninguém na obra precisa de licença do AutoCAD.
2. **O sistema sempre tem um formato legível por máquina.** É o que vai permitir,
   na Fase 3, gerar automaticamente a descrição do que mudou entre revisões. Sem
   isso, DWG e RVT são caixas-pretas e a descrição automática não existe para
   eles. Ver [roteiro.md](roteiro.md).

## Ajustando o padrão depois

Em **Configurações da obra → Padrão de nomenclatura**. Cada obra pode ter o seu;
sem padrão próprio, vale o global.

Tipos de campo disponíveis:

| Tipo | Aceita | Validação | Entra na identidade |
|---|---|---|---|
| `obra` | letras e números | tem que bater com a obra de destino | sim |
| `disciplina` | letras e números | tem que estar cadastrada | sim |
| `fase` | letras e números | tem que estar cadastrada | sim |
| `codigo` | letras, números, `.`, `-`, `_` | formato livre | sim |
| `numero` | dígitos | quantidade fixa, se configurada | sim |
| `revisao` | dígitos ou letras | numérico (`00`) ou alfabético (`A`) | não |
| `texto` | letras, números, ponto, espaço | vira o título do documento | não |

O template **obriga** um campo de revisão, um de disciplina e um de fase — sem
eles o sistema não consegue classificar o arquivo sozinho, que é o ponto todo.

Um campo `codigo` engole hífens de forma gulosa. Deixe-o próximo ao fim do
template (antes da revisão), como no padrão da TREELE, para não haver ambiguidade
com os campos seguintes.

## Migração do acervo atual

O acervo que está hoje no Mobuss e nas pastas provavelmente **não** segue o
padrão. Dois caminhos, e vale combinar antes de começar:

- **Renomear na migração.** Mais trabalho de uma vez, acervo limpo desde o
  primeiro dia. Recomendado para o que ainda está vivo em obra.
- **Cadastrar o histórico com um padrão mais frouxo.** Criar uma obra "acervo
  legado" com template permissivo e deixar o padrão rígido só para o que é novo.

Como o número da prancha agora é livre, a migração ficou consideravelmente mais
fácil: boa parte do acervo antigo deve passar sem renomear, desde que obra,
disciplina, fase e revisão estejam no lugar.

Quando chegarmos nessa etapa, dá para escrever um script que lê a estrutura de
pastas atual, propõe o nome novo de cada arquivo e mostra a lista para conferência
antes de migrar qualquer coisa.
