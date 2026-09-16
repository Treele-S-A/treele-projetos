# Nomenclatura

> **Este é o documento da Fase 0 que precisa da decisão de vocês.** O sistema já
> funciona com o padrão abaixo; o que falta é confirmar se ele é o padrão da
> TREELE ou ajustá-lo antes de cadastrar a primeira obra de verdade.

## Por que isso é o item mais importante do sistema

O nome do arquivo não é rótulo: é **o cadastro**. Quando alguém sobe
`TRL001-ARQ-PE-001-R02.pdf`, o sistema lê dali a obra, a disciplina, a fase, o
documento e a revisão, e arquiva sozinho. Ninguém preenche formulário, então
ninguém erra o preenchimento.

É por isso que arquivo fora do padrão é **recusado**, não aceito com aviso. Um
arquivo que o sistema não sabe classificar é exatamente o arquivo que some.

## O padrão atual

```
{obra}-{disciplina}-{fase}-{sequencial}-R{revisao}
```

Exemplo: `TRL001-ARQ-PE-001-R00.pdf`

| Campo | Tipo | Regra | Exemplo |
|---|---|---|---|
| `obra` | obra | Precisa ser o código da obra de destino | `TRL001` |
| `disciplina` | disciplina | Precisa existir no cadastro de disciplinas | `ARQ` |
| `fase` | fase | Precisa existir no cadastro de fases | `PE` |
| `sequencial` | numero | 3 dígitos | `001` |
| `revisao` | revisao | 2 dígitos | `00` |

Formatos aceitos: `.dwg`, `.rvt`, `.pdf`, `.ifc`.

Maiúsculas e minúsculas não importam no envio — o sistema normaliza para
maiúsculas.

### Como o código do documento é formado

O **código do documento** é a junção dos campos de identidade, sem a revisão:

```
TRL001-ARQ-PE-001-R00.pdf  →  documento TRL001-ARQ-PE-001, revisão 00
TRL001-ARQ-PE-001-R01.pdf  →  documento TRL001-ARQ-PE-001, revisão 01
```

As duas linhas acima são o **mesmo documento** em revisões diferentes. É isso que
monta o histórico automaticamente.

Campos do tipo `texto` (um título descritivo) ficam de fora da identidade de
propósito: o título pode ser corrigido entre revisões sem que o arquivo vire
outro documento.

## Ajustando o padrão

Em **Configurações da obra → Padrão de nomenclatura**. Cada obra pode ter o seu;
sem padrão próprio, vale o global.

Tipos de campo disponíveis:

| Tipo | Aceita | Validação |
|---|---|---|
| `obra` | letras e números | tem que bater com a obra de destino |
| `disciplina` | letras e números | tem que estar cadastrada |
| `fase` | letras e números | tem que estar cadastrada |
| `numero` | dígitos | quantidade fixa de dígitos, se configurada |
| `revisao` | dígitos ou letras | numérico (`00`, `01`) ou alfabético (`A`, `B`) |
| `texto` | letras, números, ponto e espaço | vira o título do documento |

O template **obriga** um campo de revisão, um de disciplina e um de fase — sem
eles o sistema não consegue classificar o arquivo sozinho, que é o ponto todo.

Campos do tipo `texto` não aceitam hífen nem underscore, para que os separadores
do template continuem delimitando os campos.

### Exemplo de padrão alternativo

```
{obra}_{disciplina}_{fase}_{seq}_REV{revisao}_{titulo}
```

com `seq` = número de 2 dígitos, `revisao` = alfabética, `titulo` = texto, aceita:

```
TRL001_EST_PE_07_REVB_Forma Pav Tipo.dwg
```

e produz: documento `TRL001-EST-PE-07`, revisão `B`, título "Forma Pav Tipo".

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

## Catálogos iniciais

Estes são um ponto de partida — **ajuste antes de cadastrar a primeira obra
real**, porque mudar um código depois invalida o nome de tudo que já subiu com
ele.

**Disciplinas:** ARQ Arquitetura · EST Estrutura · HID Hidrossanitário ·
ELE Elétrica · PCI Prevenção e Combate a Incêndio · CLI Climatização ·
TEL Telecomunicações e Cabeamento · GAS Gás · AUT Automação · TOP Topografia ·
TER Terraplenagem · PAV Pavimentação · URB Implantação e Urbanismo ·
PAI Paisagismo · INT Interiores · COO Coordenação e Compatibilização

**Fases:** LV Levantamento · EV Estudo de Viabilidade · EP Estudo Preliminar ·
AP Anteprojeto · PL Projeto Legal · PB Projeto Básico · PE Projeto Executivo ·
AB As Built

Disciplina desativada não aceita envios novos, mas o acervo já existente continua
válido e acessível.

## O que decidir

1. O template acima é o padrão da TREELE, ou vocês já têm outro em uso?
2. Revisão numérica (`R00`, `R01`) ou alfabética (`RA`, `RB`)? Há escritórios que
   usam letras para fases de estudo e números depois da aprovação — se for o caso
   de vocês, dá para ter templates diferentes por obra.
3. O sequencial de 3 dígitos é suficiente por disciplina/fase?
4. Os códigos de disciplina e fase acima batem com os de vocês?
5. Querem o título dentro do nome do arquivo (campo `texto`) ou preenchido
   depois pela interface?

## Migração do acervo atual

O acervo que está hoje no Mobuss e nas pastas provavelmente **não** segue o
padrão. Dois caminhos, e vale combinar antes de começar:

- **Renomear na migração.** Mais trabalho de uma vez, acervo limpo desde o
  primeiro dia. Recomendado para o que ainda está vivo em obra.
- **Cadastrar o histórico com um padrão mais frouxo.** Criar uma obra "acervo
  legado" com template permissivo e deixar o padrão rígido só para o que é novo.

Quando chegarmos nessa etapa, dá para escrever um script que lê a estrutura de
pastas atual, propõe o nome novo de cada arquivo e mostra a lista para conferência
antes de migrar qualquer coisa.
