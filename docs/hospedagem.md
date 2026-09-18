# Colocar no ar

Roteiro para sair da máquina do Vinicius e ir para um servidor que a equipe
inteira alcança. Leva cerca de uma hora, e a maior parte é espera.

> As senhas e o acesso ao servidor ficam com vocês. Nada neste roteiro exige
> que alguém de fora tenha credencial da TREELE.

---

## O que vai custar

O acervo de vocês tem **poucos gigabytes** — os modelos Revit continuam no
Drive, e são eles que engordariam a conta. Nessa escala tudo cabe numa máquina
só: banco, armazenamento, API e interface no mesmo servidor.

| | Por mês |
|---|---|
| VPS em São Paulo (2 vCPU, 4 GB RAM, 40 GB SSD) | ~R$ 50 a 90 |
| Domínio (`projetos.treele.com.br`) | ~R$ 3 (R$ 40/ano) |
| Backup para o OneDrive que vocês já pagam | R$ 0 |
| **Total** | **~R$ 60** |

Servidor na Europa sai por ~R$ 30, mas acrescenta ~200 ms a cada requisição.
Com três pessoas usando o dia inteiro, os R$ 30 de diferença compram a sensação
de aplicativo local. Recomendo São Paulo.

---

## 1. Contratar o servidor

Qualquer provedor com região em **São Paulo** serve. Peça:

- **Ubuntu 24.04 LTS**
- mínimo **2 vCPU, 4 GB de RAM, 40 GB de disco**
- IPv4 público
- acesso por **chave SSH**, não por senha

40 GB dão anos de folga: o crescimento de vocês é de 2 a 4 GB por ano. Quando
apertar, aumentar o disco é um clique — e se um dia o acervo explodir, dá para
mover só os arquivos para armazenamento externo trocando duas variáveis de
ambiente, sem mexer em código.

Anote o **IP** do servidor.

## 2. Apontar o domínio

No painel de DNS do domínio da TREELE, crie **dois registros A** apontando para
o IP do servidor:

| Tipo | Nome | Valor |
|---|---|---|
| A | `projetos` | `IP.DO.SERVIDOR` |
| A | `arquivos.projetos` | `IP.DO.SERVIDOR` |

São dois porque o navegador baixa e envia **direto** do armazenamento, por URL
assinada — o arquivo nunca passa pela API. A assinatura cobre o endereço, então
o armazenamento precisa de nome próprio.

O DNS pode levar de minutos a algumas horas para propagar. O instalador confere
e avisa se ainda não resolveu.

## 3. Levar o código para o servidor

**Opção A — repositório privado (recomendado).** Crie um repositório **privado**
no GitHub, envie o projeto e clone no servidor. Além de facilitar atualizações,
é uma cópia do código fora da máquina de vocês.

```bash
ssh root@IP.DO.SERVIDOR
```

```bash
mkdir -p /opt && git clone https://github.com/SUA-CONTA/treele-projetos.git /opt/treele
```

**Opção B — copiar direto.** Sem repositório, mande a pasta pelo `scp` a partir
do Windows (PowerShell, na pasta do projeto):

```bash
scp -r C:\dev\treele-projetos root@IP.DO.SERVIDOR:/opt/treele
```

Não copie `.env`, `backend/.venv`, `backend/data` nem `node_modules` — são de
desenvolvimento e atrapalham. O `.gitignore` já exclui todos na opção A.

## 4. Instalar

```bash
cd /opt/treele && sudo bash deploy/instalar-servidor.sh
```

O script pergunta o domínio e dois e-mails, e cuida do resto: instala o Docker,
fecha o firewall (só 22, 80 e 443), **gera todos os segredos sozinho**, sobe o
sistema, pede o certificado HTTPS e agenda o backup diário.

No fim ele imprime o endereço e a senha inicial do administrador. **Anote.**

Se o certificado demorar, acompanhe:

```bash
docker compose -f /opt/treele/deploy/docker-compose.prod.yml logs -f caddy
```

## 5. Primeiro acesso

Abra `https://projetos.treele.com.br`, entre com o e-mail e a senha que o script
mostrou, e **troque a senha imediatamente**.

Depois:

1. Guarde uma cópia de `/opt/treele/.env.producao` no gerenciador de senhas da
   empresa. Sem a `SECRET_KEY` dali, nenhuma sessão e nenhum link de download
   do backup voltam a funcionar.
2. Crie os usuários da equipe em **Usuários**.
3. Crie as obras e monte as equipes.

## 6. Backup para fora do servidor

O backup diário já está agendado, mas por padrão fica **no próprio servidor** —
o que não protege contra perder o servidor. Configure o envio para o OneDrive
que vocês já pagam:

```bash
sudo apt install -y rclone && rclone config
```

No assistente: `n` para novo, nomeie **exatamente** `treele-backup`, escolha
`onedrive`, e siga o login pelo navegador. Depois teste:

```bash
sudo RAIZ=/opt/treele /usr/local/bin/treele-backup
```

A última linha deve dizer *"enviado para fora do servidor"*. Se disser que o
rclone não está configurado, o nome do destino não é `treele-backup`.

## 7. Testar a restauração — não pule

Backup que nunca foi restaurado não é backup: é um arquivo grande com nome
tranquilizador. Faça isto uma vez, de preferência num segundo servidor
temporário:

```bash
sudo bash /opt/treele/deploy/restaurar.sh /var/backups/treele/treele-AAAA-MM-DD_HHMM.tar.gz
```

Depois entre no sistema, abra uma obra e **baixe um arquivo** — é o que prova
que o catálogo e os objetos voltaram juntos.

---

## Dia a dia

**Atualizar depois de uma mudança no código**

```bash
cd /opt/treele && git pull && docker compose -f deploy/docker-compose.prod.yml --env-file .env.producao up -d --build
```

As migrações de banco rodam sozinhas na subida.

**Ver o que está acontecendo**

```bash
docker compose -f /opt/treele/deploy/docker-compose.prod.yml logs -f api
```

**Abrir o console do MinIO** (não é exposto na internet, de propósito). Faça um
túnel SSH e abra `http://localhost:9001` no seu navegador:

```bash
ssh -L 9001:localhost:9001 root@IP.DO.SERVIDOR -N
```

**Espaço em disco**

```bash
df -h / && docker system df
```

---

## O que este roteiro já resolve

| Item | Como |
|---|---|
| HTTPS com certificado válido | Caddy pede ao Let's Encrypt e renova sozinho |
| `SECRET_KEY` própria | Gerada aleatoriamente na instalação |
| Postgres em vez de SQLite | Já no compose de produção |
| Migrações de esquema | Alembic, automático na subida |
| Banco e armazenamento fechados | Sem porta publicada; só 80 e 443 passam |
| Backup do banco **e** dos arquivos | Diário, 02:15, com rotação de 14 dias |
| Backup fora do servidor | rclone para o OneDrive (passo 6) |
| CORS restrito | Só o domínio real da aplicação |

Sobra um item da lista do README: **trocar a senha do administrador** depois do
primeiro acesso. Esse é com você.
