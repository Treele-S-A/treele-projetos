import { useEffect, useState } from "react";
import { Navigate, NavLink, Outlet, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { Carregando, SIMBOLO } from "./componentes";
import { useSessao } from "./sessao";
import Acervo from "./paginas/Acervo";
import Configuracoes from "./paginas/Configuracoes";
import Documento from "./paginas/Documento";
import Entrar from "./paginas/Entrar";
import Enviar from "./paginas/Enviar";
import Obras from "./paginas/Obras";
import Pasta from "./paginas/Pasta";
import Registro from "./paginas/Registro";
import Usuarios from "./paginas/Usuarios";

const CHAVE_OBRA = "treele.obra";

/** Lê a obra da URL — a moldura não tem rota própria com parâmetro. */
function obraDaUrl(caminho: string): number | null {
  const m = caminho.match(/^\/obras\/(\d+)/);
  return m ? Number(m[1]) : null;
}

/** A tela de documento não traz a obra na URL. Sem lembrar a última, a barra
 *  lateral esvaziaria justamente quando a pessoa está lendo uma revisão. */
function useObraAtiva(caminho: string): number | null {
  const daUrl = obraDaUrl(caminho);
  const [lembrada, setLembrada] = useState<number | null>(() => {
    const guardada = Number(localStorage.getItem(CHAVE_OBRA));
    return guardada || null;
  });

  useEffect(() => {
    if (daUrl) {
      localStorage.setItem(CHAVE_OBRA, String(daUrl));
      setLembrada(daUrl);
    }
  }, [daUrl]);

  return daUrl ?? lembrada;
}

function Moldura() {
  const { usuario, obras, sair } = useSessao();
  const local = useLocation();
  const navegar = useNavigate();
  const obraId = useObraAtiva(local.pathname);
  const obra = obras.find((o) => o.id === obraId) ?? null;

  const pode = (p: string) => obra?.permissoes.includes(p) ?? false;

  return (
    <div className="app">
      <nav className="prancheta">
        <div className="marca">
          <img className="marca-simbolo" src={SIMBOLO} alt="" />
          <div>
            <div className="marca-nome">Projetos</div>
            <div className="marca-sub">Treèle Construtora</div>
          </div>
        </div>

        {obras.length > 0 && (
          <div className="seletor-obra">
            <span className="rotulo">Obra</span>
            <select
              value={obra?.id ?? ""}
              onChange={(e) => navegar(`/obras/${e.target.value}/acervo`)}
            >
              <option value="" disabled>
                Selecione
              </option>
              {obras.map((o) => (
                <option key={o.id} value={o.id}>
                  {o.codigo} · {o.nome}
                </option>
              ))}
            </select>
          </div>
        )}

        <div className="menu">
          {obra ? (
            <>
              <NavLink
                to={`/obras/${obra.id}/acervo`}
                // A pasta é uma vista do acervo: o item continua marcado nela.
                className={({ isActive }) =>
                  isActive || local.pathname.startsWith(`/obras/${obra.id}/pastas/`)
                    ? "ativo"
                    : ""
                }
              >
                Acervo
              </NavLink>
              {pode("enviar") && (
                <NavLink
                  to={`/obras/${obra.id}/enviar`}
                  className={({ isActive }) => (isActive ? "ativo" : "")}
                >
                  Enviar arquivos
                </NavLink>
              )}
              {pode("gerenciar") && (
                <>
                  <NavLink
                    to={`/obras/${obra.id}/configuracoes`}
                    className={({ isActive }) => (isActive ? "ativo" : "")}
                  >
                    Configurações da obra
                  </NavLink>
                  <NavLink
                    to={`/obras/${obra.id}/registro`}
                    className={({ isActive }) => (isActive ? "ativo" : "")}
                  >
                    Registro de atividades
                  </NavLink>
                </>
              )}
              <div className="divisor" />
            </>
          ) : null}

          <NavLink to="/obras" className={({ isActive }) => (isActive ? "ativo" : "")} end>
            Todas as obras
          </NavLink>
          {usuario?.admin && (
            <NavLink to="/usuarios" className={({ isActive }) => (isActive ? "ativo" : "")}>
              Usuários
            </NavLink>
          )}
        </div>

        <div className="rodape-rail">
          <div className="nome">{usuario?.nome}</div>
          <div className="papel">
            {obra?.papel
              ? `${obra.papel[0].toUpperCase()}${obra.papel.slice(1)} nesta obra`
              : usuario?.admin
                ? "Administrador"
                : ""}
          </div>
          <button onClick={sair}>Sair</button>
        </div>
      </nav>

      <main className="area">
        <Outlet />
      </main>
    </div>
  );
}

export default function App() {
  const { usuario, carregando, obras } = useSessao();

  if (carregando) return <Carregando texto="Abrindo o acervo" />;
  if (!usuario) return <Entrar />;

  const inicial = obras.length > 0 ? `/obras/${obras[0].id}/acervo` : "/obras";

  return (
    <Routes>
      <Route element={<Moldura />}>
        <Route path="/" element={<Navigate to={inicial} replace />} />
        <Route path="/obras" element={<Obras />} />
        <Route path="/obras/:obraId/acervo" element={<Acervo />} />
        <Route path="/obras/:obraId/enviar" element={<Enviar />} />
        <Route
          path="/obras/:obraId/pastas/:disciplina/:fase"
          element={<Pasta />}
        />
        <Route path="/obras/:obraId/configuracoes" element={<Configuracoes />} />
        <Route path="/obras/:obraId/registro" element={<Registro />} />
        <Route path="/documentos/:documentoId" element={<Documento />} />
        <Route path="/usuarios" element={<Usuarios />} />
        <Route path="*" element={<Navigate to={inicial} replace />} />
      </Route>
    </Routes>
  );
}
