import { lazy, Suspense, useEffect, useState } from "react";
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
import Assistente from "./Assistente";
import { Carregando, SIMBOLO } from "./componentes";
import { CHAVE_OBRA, useSessao } from "./sessao";
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
import Atas from "./paginas/Atas";
import Ata from "./paginas/Ata";
import Fornecedores from "./paginas/Fornecedores";
import SolicitarAcesso from "./paginas/SolicitarAcesso";
import SolicitacoesAcesso from "./paginas/SolicitacoesAcesso";
import Usuarios from "./paginas/Usuarios";

// O visualizador 3D (three.js + leitor de IFC) só carrega quando alguém abre um
// modelo: o resto do sistema não paga o peso dele.
const Modelo3D = lazy(() => import("./paginas/Modelo3D"));


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

  // Pedidos de acesso de quem é de fora: só o administrador (30/10/2026).
  const pedidosAcesso = useContador(
    local.pathname, "/acesso/solicitacoes/pendentes", "pendentes", "treele:acesso",
    usuario?.admin ?? false,
  );

  const pode = (p: string) => obra?.permissoes.includes(p) ?? false;
  const admin = !!usuario?.admin;
  // Módulos (TREELE, 30/10/2026): Configurações só do administrador — o
  // engenheiro responsável vê a "Equipe da obra"; Qualidade só do
  // administrador, menos as atas, que o projetista vê (as das revisões dele).
  const equipeDoResponsavel = !admin && !!obra && pode("adicionar_membro");
  const projetista = obras.some((o) => o.papel === "projetista");

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

        {/* Três módulos (TREELE, 29/10/2026): Projetos, Configurações e
            Qualidade, cada um com o título acima da linha. Módulo sem nenhum
            item para a pessoa não aparece. */}
        <div className="menu">
          <div className="modulo-menu">Projetos</div>
          {obra && (
            <NavLink
              to={`/obras/${obra.id}/acervo`}
              className={({ isActive }) => (isActive ? "ativo" : "")}
            >
              Acervo
            </NavLink>
          )}
          {obra && pode("enviar") && (
            <NavLink
              to={`/obras/${obra.id}/enviar`}
              className={({ isActive }) => (isActive ? "ativo" : "")}
            >
              Enviar arquivos
            </NavLink>
          )}
          <NavLink to="/obras" className={({ isActive }) => (isActive ? "ativo" : "")} end>
            Todas as obras
          </NavLink>
          {obra && pode("gerenciar") && (
            <NavLink
              to={`/obras/${obra.id}/registro`}
              className={({ isActive }) => (isActive ? "ativo" : "")}
            >
              Registro de atividades
            </NavLink>
          )}
          {usuario?.admin && (
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
          )}
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

          {(admin || equipeDoResponsavel) && (
            <>
              <div className="modulo-menu">Configurações</div>
              {obra && admin && (
                <NavLink
                  to={`/obras/${obra.id}/configuracoes`}
                  className={({ isActive }) => (isActive ? "ativo" : "")}
                >
                  Configurações da obra
                </NavLink>
              )}
              {admin && (
                <>
                  <NavLink to="/usuarios" className={({ isActive }) => (isActive ? "ativo" : "")}>
                    Usuários
                  </NavLink>
                  <NavLink
                    to="/solicitacoes-acesso"
                    className={({ isActive }) => `com-contador ${isActive ? "ativo" : ""}`}
                  >
                    Solicitações de acesso
                    <Contador
                      total={pedidosAcesso}
                      rotulo={(n) => (n === 1 ? "1 aguardando análise" : `${n} aguardando análise`)}
                    />
                  </NavLink>
                </>
              )}
              {/* Engenheiro responsável que não é administrador: só a equipe. */}
              {equipeDoResponsavel && (
                <NavLink
                  to={`/obras/${obra!.id}/configuracoes`}
                  className={({ isActive }) => (isActive ? "ativo" : "")}
                >
                  Equipe da obra
                </NavLink>
              )}
            </>
          )}

          {(admin || projetista) && (
            <>
              <div className="modulo-menu">Qualidade</div>
              <NavLink to="/atas" className={({ isActive }) => (isActive ? "ativo" : "")}>
                Atas de análise crítica
              </NavLink>
              {admin && (
                <NavLink
                  to="/fornecedores"
                  className={({ isActive }) => (isActive ? "ativo" : "")}
                >
                  Fornecedores de projetos
                </NavLink>
              )}
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
            <button
              onClick={() => {
                // Volta ao início antes de sair: quem entrar depois começa na
                // tela de obras, não na última que a pessoa anterior abriu.
                navegar("/", { replace: true });
                sair();
              }}
            >
              Sair
            </button>
          </div>
        </div>
      </nav>

      <main className="area">
        <AvisoVersaoNova />
        <Outlet />
      </main>
      <Assistente obraId={obraId} />
    </div>
  );
}

export default function App() {
  const { usuario, carregando } = useSessao();
  const local = useLocation();

  if (carregando) return <Carregando texto="Abrindo o acervo" />;
  // Sem login, só a entrada e o pedido de acesso (30/10/2026).
  if (!usuario) return local.pathname === "/solicitar-acesso" ? <SolicitarAcesso /> : <Entrar />;

  // Toda entrada começa na carteira de obras (TREELE, 06/10/2026). Link de
  // e-mail é exceção natural: ele já traz o endereço, e não passa por aqui.
  const inicial = "/obras";

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
        <Route
          path="/modelos"
          element={
            <Suspense fallback={<Carregando texto="Abrindo o visualizador 3D" />}>
              <Modelo3D />
            </Suspense>
          }
        />
        <Route path="/usuarios" element={<Usuarios />} />
        <Route path="/conta" element={<Conta />} />
        <Route path="/notificacoes" element={<Notificacoes />} />
        <Route path="/solicitacoes" element={<SolicitacoesGerais />} />
        <Route path="/atas" element={<Atas />} />
        <Route path="/atas/:ataId" element={<Ata />} />
        <Route path="/fornecedores" element={<Fornecedores />} />
        <Route path="/solicitacoes-acesso" element={<SolicitacoesAcesso />} />
        <Route path="/solicitar-acesso" element={<Navigate to="/obras" replace />} />
        <Route path="*" element={<Navigate to={inicial} replace />} />
      </Route>
    </Routes>
  );
}
