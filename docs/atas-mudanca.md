# Atas de mudança de projeto

Módulo Qualidade, desde 25/11/2026. Não confundir com a ata de análise crítica
(PRO-FL-005): a ata de mudança registra uma alteração técnica adotada e chega
pronta, em PDF.

## Como funciona

- A tela **Atas de mudança de projeto** lista as obras que a pessoa coordena
  (o administrador vê todas). Cada obra abre com as atas por disciplina.
- **Enviar atas**: um ou vários PDFs, com qualquer nome, e a disciplina. Com um
  só, dá para escrever o assunto (opcional; editável depois na lista). A
  janela mostra antes o nome que cada arquivo vai ganhar.
- O sistema numera na ordem em que as atas chegam, por obra e disciplina:
  `SER-HID-AMP01-R00`, `SER-HID-AMP02-R00`, `MIL-ARQ-AMP01-R00`. O número é
  dado quando o arquivo termina de subir: envio abandonado não deixa buraco.
- **Nova revisão**: um PDF por vez; vira `R01`, `R02`…
- **Excluir**: uma revisão (o × ao lado das anteriores ou "Excluir R01") ou a
  ata inteira. Apaga o PDF de vez. Excluir a única revisão leva a ata junto.
  O número só volta a ser usado se era o último (excluir a AMP02 de três
  deixa o buraco; excluir a AMP03 faz a próxima ser AMP03 de novo).
- Abrir e baixar trazem o PDF com o nome do sistema (`SER-HID-AMP01-R01.pdf`).
- Fica na trilha de auditoria: `ata_mudanca_enviada` e `ata_mudanca_excluida`.

## Quem pode

Coordenadores da obra e administrador, como no cronograma. Projetista, obra e
comercial não veem a tela, e o servidor recusa (403).

## Código

- `backend/app/api/atas_mudanca.py`; modelos `AtaMudanca` e
  `AtaMudancaRevisao` (`models.py`); migração `b3d5f7a9c1e2`.
- O PDF sobe direto para o armazenamento (`obras/<obra>/_atas_mudanca/`), como
  os arquivos de projeto: `POST /obras/{id}/atas-mudanca/envios` →
  envio para a URL assinada → `POST /atas-mudanca/envios/{id}/confirmar`.
- Rotas: `GET /atas-mudanca/obras`, `GET /obras/{id}/atas-mudanca`,
  `GET /atas-mudanca/revisoes/{id}/visualizar[?baixar=true]`,
  `PATCH /atas-mudanca/{id}` (assunto), `DELETE /atas-mudanca/revisoes/{id}`,
  `DELETE /atas-mudanca/{id}`.
- Tela: `frontend/src/paginas/AtasMudanca.tsx`. Testes:
  `backend/tests/test_atas_mudanca.py`.
