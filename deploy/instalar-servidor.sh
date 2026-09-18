#!/usr/bin/env bash
# Prepara um servidor Ubuntu novo e sobe o sistema.
#
#   sudo bash deploy/instalar-servidor.sh
#
# Pode rodar de novo sem medo: o que já está feito é pulado, e o .env.producao
# existente nunca é sobrescrito — senão a SECRET_KEY mudaria e todas as sessões
# e links de download cairiam.

set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_ARQ="$RAIZ/.env.producao"

vermelho() { printf '\033[31m%s\033[0m\n' "$*"; }
verde() { printf '\033[32m%s\033[0m\n' "$*"; }
titulo() { printf '\n\033[1m== %s ==\033[0m\n' "$*"; }

[ "$(id -u)" -eq 0 ] || { vermelho "Rode com sudo."; exit 1; }

# --------------------------------------------------------------------------
titulo "1/6  Pacotes do sistema"
# --------------------------------------------------------------------------
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq ca-certificates curl gnupg ufw openssl >/dev/null

if ! command -v docker >/dev/null; then
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
    | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  chmod a+r /etc/apt/keyrings/docker.gpg
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update -qq
  apt-get install -y -qq docker-ce docker-ce-cli containerd.io \
    docker-buildx-plugin docker-compose-plugin >/dev/null
  verde "Docker instalado."
else
  verde "Docker já estava instalado."
fi

systemctl enable --now docker >/dev/null 2>&1 || true

# --------------------------------------------------------------------------
titulo "2/6  Firewall"
# --------------------------------------------------------------------------
# Só SSH e web. Banco e armazenamento não têm porta aberta para a internet —
# eles só existem dentro da rede do Docker.
ufw allow OpenSSH >/dev/null
ufw allow 80/tcp >/dev/null
ufw allow 443/tcp >/dev/null
ufw --force enable >/dev/null
verde "Aberto: 22, 80 e 443. Todo o resto bloqueado."

# --------------------------------------------------------------------------
titulo "3/6  Configuração"
# --------------------------------------------------------------------------
if [ -f "$ENV_ARQ" ]; then
  verde "$ENV_ARQ já existe — mantido como está."
else
  read -rp "Domínio da aplicação (ex.: projetos.treele.com.br): " DOMINIO
  read -rp "Domínio dos arquivos [arquivos.$DOMINIO]: " DOMINIO_ARQUIVOS
  DOMINIO_ARQUIVOS="${DOMINIO_ARQUIVOS:-arquivos.$DOMINIO}"
  read -rp "E-mail para avisos do certificado: " ACME_EMAIL
  read -rp "E-mail do administrador do sistema: " ADMIN_EMAIL

  segredo() { openssl rand -base64 36 | tr -d '\n/+=' | cut -c1-40; }
  ADMIN_SENHA="$(segredo | cut -c1-16)"

  cat > "$ENV_ARQ" <<EOF
# Gerado por deploy/instalar-servidor.sh em $(date -Iseconds).
# NÃO versione este arquivo. Guarde uma cópia em lugar seguro: sem a
# SECRET_KEY o sistema não valida nenhuma sessão nem link de download.

DOMINIO=$DOMINIO
DOMINIO_ARQUIVOS=$DOMINIO_ARQUIVOS
ACME_EMAIL=$ACME_EMAIL

SECRET_KEY=$(segredo)
POSTGRES_PASSWORD=$(segredo)
S3_ACCESS_KEY=treele
S3_SECRET_KEY=$(segredo)
S3_BUCKET=treele-projetos

ADMIN_EMAIL=$ADMIN_EMAIL
ADMIN_SENHA=$ADMIN_SENHA

TAMANHO_MAX_MB=2048
EOF
  chmod 600 "$ENV_ARQ"
  verde "$ENV_ARQ criado, com segredos aleatórios."
fi

set -a; . "$ENV_ARQ"; set +a

# --------------------------------------------------------------------------
titulo "4/6  DNS"
# --------------------------------------------------------------------------
IP_SERVIDOR="$(curl -fsS --max-time 10 https://api.ipify.org || echo '?')"
conferir_dns() {
  local nome="$1" resolvido
  resolvido="$(getent ahostsv4 "$nome" 2>/dev/null | awk 'NR==1{print $1}')"
  if [ "$resolvido" = "$IP_SERVIDOR" ]; then
    verde "  $nome -> $resolvido  OK"
  else
    vermelho "  $nome -> ${resolvido:-não resolve}  (esperado $IP_SERVIDOR)"
    return 1
  fi
}

echo "IP deste servidor: $IP_SERVIDOR"
dns_ok=true
conferir_dns "$DOMINIO" || dns_ok=false
conferir_dns "$DOMINIO_ARQUIVOS" || dns_ok=false

if [ "$dns_ok" = false ]; then
  vermelho ""
  vermelho "Aponte os dois nomes (registro A) para $IP_SERVIDOR antes de seguir."
  vermelho "Sem DNS correto o Let's Encrypt recusa o certificado, e tentativas"
  vermelho "repetidas consomem o limite semanal dele."
  read -rp "Continuar mesmo assim? [s/N] " r
  [ "${r,,}" = "s" ] || exit 1
fi

# --------------------------------------------------------------------------
titulo "5/6  Subindo o sistema"
# --------------------------------------------------------------------------
cd "$RAIZ"

# Confere a configuração do proxy ANTES de subir. Um erro aqui, sem esta
# checagem, viraria um contêiner reiniciando em laço e um "site fora do ar"
# sem explicação nenhuma na tela.
echo "Conferindo a configuração do proxy..."
if ! docker run --rm   -e DOMINIO="$DOMINIO" -e DOMINIO_ARQUIVOS="$DOMINIO_ARQUIVOS" -e ACME_EMAIL="$ACME_EMAIL"   -v "$RAIZ/deploy/Caddyfile:/etc/caddy/Caddyfile:ro"   caddy:2-alpine caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile; then
  vermelho "A configuração do Caddy (deploy/Caddyfile) tem erro. Nada foi iniciado."
  exit 1
fi
verde "Configuração do proxy válida."

docker compose -f deploy/docker-compose.prod.yml --env-file "$ENV_ARQ" up -d --build

# --------------------------------------------------------------------------
titulo "6/6  Backup diário"
# --------------------------------------------------------------------------
install -m 0755 "$RAIZ/deploy/backup.sh" /usr/local/bin/treele-backup
mkdir -p /var/backups/treele
cat > /etc/cron.d/treele-backup <<EOF
# Backup do TREELE, todo dia às 02:15.
15 2 * * * root RAIZ=$RAIZ /usr/local/bin/treele-backup >> /var/log/treele-backup.log 2>&1
EOF
verde "Backup diário agendado (02:15). Log em /var/log/treele-backup.log"

# --------------------------------------------------------------------------
titulo "Pronto"
# --------------------------------------------------------------------------
cat <<EOF

  Sistema:  https://$DOMINIO
  Entrar:   $ADMIN_EMAIL
  Senha:    $ADMIN_SENHA

O certificado pode levar um minuto para sair na primeira subida.
Acompanhe com:  docker compose -f deploy/docker-compose.prod.yml logs -f caddy

FAÇA AGORA, nesta ordem:
  1. Entre no sistema e troque a senha do administrador.
  2. Guarde uma cópia de $ENV_ARQ num lugar seguro (gerenciador de senhas).
  3. Teste a restauração do backup pelo menos uma vez — ver docs/hospedagem.md.

EOF
