#!/usr/bin/env bash
# Backup diário: banco + arquivos.
#
#   RAIZ=/opt/treele /usr/local/bin/treele-backup
#
# São duas coisas distintas e as duas são obrigatórias. O dump do Postgres traz
# o catálogo, as revisões e a auditoria; os arquivos ficam no MinIO. Um sem o
# outro é um acervo com o índice e sem as pranchas, ou o contrário.
#
# Ordem: o banco é despejado primeiro. Se um arquivo entrar entre o dump e a
# cópia dos objetos, sobra um objeto sem linha no catálogo — que é inofensivo.
# Ao contrário sobraria linha apontando para arquivo inexistente.

set -euo pipefail

RAIZ="${RAIZ:-/opt/treele}"
DESTINO="${DESTINO:-/var/backups/treele}"
MANTER_DIAS="${MANTER_DIAS:-14}"
COMPOSE="docker compose -f $RAIZ/deploy/docker-compose.prod.yml --env-file $RAIZ/.env.producao"

carimbo="$(date +%Y-%m-%d_%H%M)"
trabalho="$DESTINO/.parcial-$carimbo"
final="$DESTINO/treele-$carimbo.tar.gz"

mkdir -p "$trabalho"
# Parcial nunca fica para trás, nem se o script morrer no meio.
trap 'rm -rf "$trabalho"' EXIT

echo "[$(date -Iseconds)] iniciando"

# 1. Banco -------------------------------------------------------------------
$COMPOSE exec -T db pg_dump -U treele --format=custom treele > "$trabalho/banco.dump"
echo "  banco: $(du -h "$trabalho/banco.dump" | cut -f1)"

# 2. Arquivos ----------------------------------------------------------------
# Cópia direta do volume do MinIO. Traz a estrutura inteira do bucket, que é
# legível: obras/CODIGO/DOCUMENTO/Rxx/arquivo. Se um dia for preciso resgatar
# tudo sem o sistema, a árvore de pastas já conta a história.
$COMPOSE exec -T minio tar -cf - -C /data . > "$trabalho/arquivos.tar"
echo "  arquivos: $(du -h "$trabalho/arquivos.tar" | cut -f1)"

# 3. Configuração ------------------------------------------------------------
# Sem a SECRET_KEY o backup restaura, mas ninguém entra.
cp "$RAIZ/.env.producao" "$trabalho/env.producao"

# 4. Empacota ----------------------------------------------------------------
tar -czf "$final" -C "$trabalho" .
chmod 600 "$final"
echo "  pacote: $final ($(du -h "$final" | cut -f1))"

# 5. Cópia fora do servidor --------------------------------------------------
# Backup que só existe na máquina que pode pegar fogo não é backup.
# Configure o rclone uma vez (ver docs/hospedagem.md) e o envio passa a ser
# automático. Sem rclone, o script continua — mas avisa.
if command -v rclone >/dev/null && rclone listremotes 2>/dev/null | grep -q '^treele-backup:'; then
  rclone copy "$final" treele-backup:treele-backup/ --quiet
  echo "  enviado para fora do servidor"
else
  echo "  AVISO: rclone não configurado — backup existe só neste servidor."
fi

# 6. Rotação -----------------------------------------------------------------
find "$DESTINO" -name 'treele-*.tar.gz' -mtime "+$MANTER_DIAS" -delete
echo "[$(date -Iseconds)] concluído — $(ls -1 "$DESTINO"/treele-*.tar.gz 2>/dev/null | wc -l) cópias guardadas"
