import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, ErroApi, formatarData, type Notificacao } from "../api";
import { Aviso, Carregando, Vazio } from "../componentes";

/** Avisa o menu que a contagem mudou — ele busca de novo. */
export function contagemMudou() {
  window.dispatchEvent(new Event("treele:notificacoes"));
}

export default function Notificacoes() {
  const navegar = useNavigate();
  const [lista, setLista] = useState<Notificacao[] | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  async function carregar() {
    try {
      setLista(await api.get<Notificacao[]>("/notificacoes"));
    } catch (ex) {
      setErro(ex instanceof ErroApi ? ex.message : "Não foi possível carregar as notificações.");
    }
  }

  useEffect(() => {
    void carregar();
  }, []);

  async function abrir(n: Notificacao) {
    if (!n.lida) {
      // Abrir não espera a marcação: se ela falhar, o aviso só segue como não lido.
      api.post(`/notificacoes/${n.id}/lida`).then(contagemMudou, () => {});
    }
    if (n.tipo === "solicitacao_acesso") navegar("/solicitacoes-acesso");
    else if (n.documento_id) navegar(`/documentos/${n.documento_id}`);
  }

  async function marcarTodas() {
    try {
      await api.post("/notificacoes/lidas");
      contagemMudou();
      await carregar();
    } catch (ex) {
      setErro(ex instanceof ErroApi ? ex.message : "Não foi possível marcar como lidas.");
    }
  }

  const naoLidas = lista?.filter((n) => !n.lida).length ?? 0;

  return (
    <>
      <div className="cabecalho-area">
        <div>
          <span className="rotulo">
            {naoLidas === 0 ? "Tudo lido" : naoLidas === 1 ? "1 não lida" : `${naoLidas} não lidas`}
          </span>
          <h1>Notificações</h1>
        </div>
        {naoLidas > 0 && (
          <button className="botao secundario" onClick={marcarTodas}>
            Marcar todas como lidas
          </button>
        )}
      </div>

      {erro && <Aviso tom="erro">{erro}</Aviso>}
      {lista === null && !erro && <Carregando texto="Buscando os avisos" />}
      {lista?.length === 0 && (
        <Vazio titulo="Nenhuma notificação">
          <span className="silencioso">
            Pedidos de revisão e revisões liberadas para obra aparecem aqui.
          </span>
        </Vazio>
      )}

      {lista && lista.length > 0 && (
        <div className="folha">
          <div className="folha-corpo lista-avisos">
            {lista.map((n) => (
              <button
                key={n.id}
                className={`aviso-item ${n.lida ? "lida" : "nao-lida"}`}
                onClick={() => abrir(n)}
                title="Abrir o documento"
              >
                <span className="aviso-ponto" aria-label={n.lida ? "Lida" : "Não lida"} />
                <span className="aviso-corpo">
                  <span className="aviso-topo">
                    <strong>{n.titulo}</strong>
                    <span className="silencioso">
                      <span className="mono">{n.obra_codigo ?? "Acesso"}</span> · {formatarData(n.criada_em)}
                    </span>
                  </span>
                  <span className="aviso-texto">{n.texto}</span>
                </span>
              </button>
            ))}
          </div>
        </div>
      )}
    </>
  );
}
