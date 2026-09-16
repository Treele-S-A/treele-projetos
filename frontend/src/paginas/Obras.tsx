import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { api, ErroApi, ROTULO_PAPEL } from "../api";
import { Aviso, Vazio } from "../componentes";
import { useSessao } from "../sessao";

export default function Obras() {
  const { obras, usuario, recarregarObras } = useSessao();
  const [abrindoForm, setAbrindoForm] = useState(false);
  const [codigo, setCodigo] = useState("");
  const [nome, setNome] = useState("");
  const [cliente, setCliente] = useState("");
  const [erro, setErro] = useState<ErroApi | null>(null);
  const [salvando, setSalvando] = useState(false);

  async function criar(e: FormEvent) {
    e.preventDefault();
    setErro(null);
    setSalvando(true);
    try {
      await api.post("/obras", {
        codigo: codigo.trim().toUpperCase(),
        nome: nome.trim(),
        cliente: cliente.trim() || null,
      });
      await recarregarObras();
      setAbrindoForm(false);
      setCodigo("");
      setNome("");
      setCliente("");
    } catch (ex) {
      setErro(ex instanceof ErroApi ? ex : new ErroApi(0, "Não foi possível criar a obra."));
    } finally {
      setSalvando(false);
    }
  }

  return (
    <>
      <div className="cabecalho-area">
        <div>
          <span className="rotulo">Carteira</span>
          <h1>Obras</h1>
        </div>
        {usuario?.admin && (
          <button className="botao" onClick={() => setAbrindoForm((v) => !v)}>
            {abrindoForm ? "Cancelar" : "Nova obra"}
          </button>
        )}
      </div>

      {abrindoForm && (
        <div className="folha">
          <div className="folha-titulo">
            <strong>Nova obra</strong>
          </div>
          <form className="folha-corpo" onSubmit={criar}>
            {erro && <Aviso tom="erro" titulo={erro.message} itens={erro.erros} />}
            <div className="filtros">
              <label className="campo">
                <span className="rotulo">Código</span>
                <input
                  value={codigo}
                  onChange={(e) => setCodigo(e.target.value)}
                  placeholder="TRL001"
                  pattern="[A-Za-z0-9]+"
                  title="Só letras e números — este código aparece no nome de cada arquivo."
                  required
                />
              </label>
              <label className="campo">
                <span className="rotulo">Nome</span>
                <input
                  value={nome}
                  onChange={(e) => setNome(e.target.value)}
                  placeholder="Residencial Aurora"
                  required
                />
              </label>
              <label className="campo">
                <span className="rotulo">Cliente</span>
                <input value={cliente} onChange={(e) => setCliente(e.target.value)} />
              </label>
            </div>
            <p className="silencioso" style={{ fontSize: 12, margin: "12px 0 0" }}>
              O código entra na nomenclatura dos arquivos desta obra. Escolha agora com
              cuidado: mudá-lo depois invalida o nome de tudo que já subiu.
            </p>
            <div style={{ marginTop: 14 }}>
              <button className="botao" disabled={salvando}>
                {salvando ? "Criando…" : "Criar obra"}
              </button>
            </div>
          </form>
        </div>
      )}

      <div className="folha">
        {obras.length === 0 ? (
          <Vazio titulo="Nenhuma obra ainda">
            {usuario?.admin
              ? "Crie a primeira obra para começar o acervo."
              : "Peça ao coordenador para incluir você na equipe de uma obra."}
          </Vazio>
        ) : (
          <div className="tabela-rolagem">
            <table className="tabela">
              <thead>
                <tr>
                  <th>Código</th>
                  <th>Nome</th>
                  <th>Cliente</th>
                  <th>Seu papel</th>
                </tr>
              </thead>
              <tbody>
                {obras.map((o) => (
                  <tr key={o.id}>
                    <td>
                      <Link className="link-doc" to={`/obras/${o.id}/acervo`}>
                        {o.codigo}
                      </Link>
                    </td>
                    <td>{o.nome}</td>
                    <td className="silencioso">{o.cliente ?? "—"}</td>
                    <td className="silencioso">
                      {o.papel ? ROTULO_PAPEL[o.papel] : usuario?.admin ? "Administrador" : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  );
}
