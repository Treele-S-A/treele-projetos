import { useEffect, useState } from "react";
import {
  Navigate,
  NavLink,
  Outlet,
  Route,
  Routes,
  useLocation,
  useNavigate,
  useParams,
} from "react-router-dom";
import { api } from "./api";
import { Carregando, SIMBOLO } from "./componentes";
import { useSessao } from "./sessao";
import Acervo from "./paginas/Acervo";
import Configuracoes from "./paginas/Configuracoes";
import Conta from "./paginas/Conta";
import Documento from "./paginas/Documento";
import Entrar from "./paginas/Entrar";
import Enviar from "./paginas/Enviar";
import Notificacoes from "./paginas/Notificacoes";
import Obras from "./paginas/Obras";
import Registro from "./paginas/Registro";
import SolicitacoesGerais from "./paginas/SolicitacoesGerais";
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

/** Um contador do menu. Busca a cada troca de tela, a cada minuto e quando
 *  alguma tela avisa que ele mudou (o evento). Desligado, não busca nada. */
function useContador(
  caminho: string,
  endereco: string,
  campo: string,
  evento: string,
  ligado = true,
): number {
  const [total, setTotal] = useState(0);

  useEffect(() => {
    if (!ligado) return;
    let vivo = true;
    const buscar = () =>
      api
        .get<Record<string, number>>(endereco)
        .then((r) => vivo && setTotal(r[campo] ?? 0))
        .catch(() => {});
    buscar();
    const relogio = window.setInterval(buscar, 60_000);
    window.addEventListener(evento, buscar);
    return () => {
      vivo = false;
      window.clearInterval(relogio);
      window.removeEventListener(evento, buscar);
    };
  }, [caminho, endereco, campo, evento, ligado]);

  return total;
}

function Contador({ total, rotulo }: { total: number; rotulo: (n: number) => string }) {
  if (total <= 0) return null;
  return (
    <span className="contador" aria-label={rotulo(total)}>
      {total > 99 ? "99+" : total}
    </span>
  );
}

/** A tela própria de pasta deixou de existir (06/10/2026): a fase abre na
 *  árvore do acervo. Link antigo (favorito, e-mail) cai nela, já aberta. */
function PastaAntiga() {
  const { obraId, disciplina, fase } = useParams();
  return <Navigate to={`/obras/${obraId}/acervo?pasta=${disciplina}/${fase}`} replace />;
}

/** Faixa no topo quando a tela ficou para trás de uma atualização. */
function AvisoVersaoNova() {
  const [nova, setNova] = useState(false);
  useEffect(() => {
    const aoDetectar = () => setNova(true);
    window.addEventListener("treele:versao-nova", aoDetectar);
    return () => window.removeEventListener("treele:versao-nova", aoDetectar);
  }, []);
  if (!nova) return null;
  return (
    <div className="aviso-versao" role="status">
      <span>Saiu uma versão nova do sistema. Recarregue para usar a mais recente.</span>
      <button className="botao pequeno" onClick={() => window.location.reload()}>
        Recarregar
      </button>
    </div>
  );
}

function Moldura() {
  const { usuario, obras, sair } = useSessao();
  const local = useLocation();
  const navegar = useNavigate();
  const obraId = useObraAtiva(local.pathname);
  const obra = obras.find((o) => o.id === obraId) ?? null;
  const naoLidas = useContador(
    local.pathname, "/notificacoes/contagem", "nao_lidas", "treele:notificacoes",
  );
  // Pedidos esperando autorização, de todas as obras: só o administrador vê.
  const aguardando = useContador(
    local.pathname, "/solicitacoes/contagem", "aguardando", "treele:solicitacoes",
    usuario?.admin ?? false,
  );

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
                className={({ isActive }) => (isActive ? "ativo" : "")}
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
              {/* Engenheiro responsável sem papel de coordenador: só a equipe. */}
              {!pode("gerenciar") && pode("adicionar_membro") && (
                <NavLink
                  to={`/obras/${obra.id}/configuracoes`}
                  className={({ isActive }) => (isActive ? "ativo" : "")}
                >
                  Equipe da obra
                </NavLink>
              )}
              <div className="divisor" />
            </>
          ) : null}

          <NavLink to="/obras" className={({ isActive }) => (isActive ? "ativo" : "")} end>
            Todas as obras
          </NavLink>
          {!usuario?.comercial && (
            <NavLink
              to="/notificacoes"
              className={({ isActive }) => `com-contador ${isActive ? "ativo" : ""}`}
            >
              Notificações
              <Contador
                total={naoLidas}
                rotulo={(n) => (n === 1 ? "1 não lida" : `${n} não lidas`)}
              />
            </NavLink>
          )}
          {usuario?.admin && (
            <>
              <NavLink
                to="/solicitacoes"
                className={({ isActive }) => `com-contador ${isActive ? "ativo" : ""}`}
              >
                Solicitações de revisão
                <Contador
                  total={aguardando}
                  rotulo={(n) =>
                    n === 1 ? "1 aguardando autorização" : `${n} aguardando autorização`
                  }
                />
              </NavLink>
              <NavLink to="/usuarios" className={({ isActive }) => (isActive ? "ativo" : "")}>
                Usuários
              </NavLink>
            </>
          )}
        </div>

        <div className="rodape-rail">
          <div className="nome">{usuario?.nome}</div>
          <div className="papel">
            {obra?.papel
              ? `${obra.papel[0].toUpperCase()}${obra.papel.slice(1)} nesta obra`
              : usuario?.admin
                ? "Administrador"
                : usuario?.comercial
                  ? "Comercial"
                  : ""}
          </div>
          <div className="acoes">
            <NavLink to="/conta" className={({ isActive }) => (isActive ? "ativo" : "")}>
              Minha conta
            </NavLink>
            <button onClick={sair}>Sair</button>
          </div>
        </div>
      </nav>

      <main className="area">
        <AvisoVersaoNova />
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
          element={<PastaAntiga />}
        />
        <Route path="/obras/:obraId/configuracoes" element={<Configuracoes />} />
        <Route path="/obras/:obraId/registro" element={<Registro />} />
        <Route path="/documentos/:documentoId" element={<Documento />} />
        <Route path="/usuarios" element={<Usuarios />} />
        <Route path="/conta" element={<Conta />} />
        <Route path="/notificacoes" element={<Notificacoes />} />
        <Route path="/solicitacoes" element={<SolicitacoesGerais />} />
        <Route path="*" element={<Navigate to={inicial} replace />} />
      </Route>
    </Routes>
  );
}
