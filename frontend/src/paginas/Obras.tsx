import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { api, ErroApi, ROTULO_PAPEL } from "../api";
import { Aviso, CapaObra, Vazio } from "../componentes";
import { useSessao } from "../sessao";

export default function Obras() {
  const { obras, usuario, recarregarObras } = useSessao();
  const [abrindoForm, setAbrindoForm] = useState(false);
  const [codigo, setCodigo] = useState("");
  const [nome, setNome] = useState("");
  const [cliente, setCliente] = useState("");
  const [endereco, setEndereco] = useState("");
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
        endereco: endereco.trim(),
      });
      await recarregarObras();
      setAbrindoForm(false);
      setCodigo("");
      setNome("");
      setCliente("");
      setEndereco("");
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
              <label className="campo" style={{ flex: "1 1 100%" }}>
                <span className="rotulo">Endereço</span>
                <input
                  value={endereco}
                  onChange={(e) => setEndereco(e.target.value)}
                  placeholder="Rua João Mazzarotto, 526 – Capão Raso – Curitiba – PR"
                  minLength={5}
                  maxLength={300}
                  title="Vai na ata de análise crítica dos projetos."
                  required
                />
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

      {obras.length === 0 ? (
        <div className="folha">
          <Vazio titulo="Nenhuma obra ainda">
            {usuario?.admin
              ? "Crie a primeira obra para começar o acervo."
              : "Peça ao coordenador para incluir você na equipe de uma obra."}
          </Vazio>
        </div>
      ) : (
        <div className="obras-grade" style={{ marginTop: abrindoForm ? 16 : 0 }}>
          {obras.map((o) => (
            <Link key={o.id} className="cartao-obra" to={`/obras/${o.id}/acervo`}>
              {/* O nome vem na capa, então o logo é decorativo (alt vazio). */}
              <CapaObra obra={o}>
                <span className="capa-textos">
                  <span className="codigo">{o.codigo}</span>
                  <span className="nome-obra">{o.nome}</span>
                </span>
                <span className="capa-seta" aria-hidden="true">→</span>
              </CapaObra>
              <span className="pe">
                {/* Vazio sem cliente: o papel continua alinhado à direita. */}
                <span>{o.cliente}</span>
                <span>
                  {o.papel
                    ? ROTULO_PAPEL[o.papel]
                    : usuario?.admin
                      ? "Administrador"
                      : usuario?.comercial
                        ? "Comercial"
                        : ""}
                </span>
              </span>
            </Link>
          ))}
        </div>
      )}
    </>
  );
}
