#!/usr/bin/env bash
# Restaura um backup. Sobrescreve banco e arquivos.
#
#   sudo bash deploy/restaurar.sh /var/backups/treele/treele-2026-09-18_0215.tar.gz
#
# Backup que nunca foi restaurado não é backup: é um arquivo grande com nome
# tranquilizador. Rode isto uma vez, num servidor de teste, antes de precisar.

set -euo pipefail

PACOTE="${1:-}"
RAIZ="${RAIZ:-/opt/treele}"
COMPOSE="docker compose -f $RAIZ/deploy/docker-compose.prod.yml --env-file $RAIZ/.env.producao"

vermelho() { printf '\033[31m%s\033[0m\n' "$*"; }

[ -f "$PACOTE" ] || { vermelho "Uso: $0 <arquivo.tar.gz>"; exit 1; }

trabalho="$(mktemp -d)"
trap 'rm -rf "$trabalho"' EXIT
tar -xzf "$PACOTE" -C "$trabalho"

[ -f "$trabalho/banco.dump" ] || { vermelho "Pacote sem banco.dump."; exit 1; }
[ -f "$trabalho/arquivos.tar" ] || { vermelho "Pacote sem arquivos.tar."; exit 1; }

cat <<EOF

Vai restaurar:
  banco     $(du -h "$trabalho/banco.dump" | cut -f1)
  arquivos  $(du -h "$trabalho/arquivos.tar" | cut -f1)

O conteúdo ATUAL do banco e do armazenamento será substituído.
EOF
read -rp "Digite RESTAURAR para confirmar: " r
[ "$r" = "RESTAURAR" ] || { echo "Cancelado."; exit 1; }

echo "== parando a aplicação =="
# API parada durante a troca: ninguém escreve no banco enquanto ele é recriado.
$COMPOSE stop api web

echo "== banco =="
$COMPOSE exec -T db dropdb -U treele --if-exists --force treele
$COMPOSE exec -T db createdb -U treele treele
$COMPOSE exec -T db pg_restore -U treele -d treele --no-owner < "$trabalho/banco.dump"

echo "== arquivos =="
$COMPOSE exec -T minio sh -c 'rm -rf /data/* /data/.minio.sys'
$COMPOSE exec -T minio tar -xf - -C /data < "$trabalho/arquivos.tar"
$COMPOSE restart minio

echo "== subindo a aplicação =="
$COMPOSE start api web

cat <<EOF

Restaurado.

Confira antes de liberar para a equipe:
  - entre no sistema e abra uma obra
  - baixe um arquivo, para ver se o objeto veio junto com o catálogo

Se as senhas pararam de funcionar, a SECRET_KEY deste servidor é diferente da
do backup. O pacote traz a original em env.producao.

EOF
