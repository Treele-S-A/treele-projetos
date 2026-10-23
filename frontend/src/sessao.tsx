import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { api, gravarToken, lerToken, type Catalogo, type Obra, type Usuario } from "./api";

/** A obra que a barra lateral lembra entre uma tela e outra (App.tsx). É da
 *  pessoa, não do navegador: sai junto com a sessão. */
export const CHAVE_OBRA = "treele.obra";

interface Sessao {
  usuario: Usuario | null;
  obras: Obra[];
  disciplinas: Catalogo[];
  fases: Catalogo[];
  carregando: boolean;
  entrar(email: string, senha: string, manterConectado?: boolean): Promise<void>;
  sair(): void;
  recarregarObras(): Promise<void>;
}

const Contexto = createContext<Sessao | null>(null);

export function ProvedorSessao({ children }: { children: ReactNode }) {
  const [usuario, setUsuario] = useState<Usuario | null>(null);
  const [obras, setObras] = useState<Obra[]>([]);
  const [disciplinas, setDisciplinas] = useState<Catalogo[]>([]);
  const [fases, setFases] = useState<Catalogo[]>([]);
  const [carregando, setCarregando] = useState(true);

  const carregarTudo = useCallback(async () => {
    const [eu, listaObras, listaDisciplinas, listaFases] = await Promise.all([
      api.get<Usuario>("/auth/eu"),
      api.get<Obra[]>("/obras"),
      api.get<Catalogo[]>("/disciplinas"),
      api.get<Catalogo[]>("/fases"),
    ]);
    setUsuario(eu);
    setObras(listaObras);
    setDisciplinas(listaDisciplinas);
    setFases(listaFases);
  }, []);

  useEffect(() => {
    const fragmento = new URLSearchParams(window.location.hash.slice(1));
    const tokenMicrosoft = fragmento.get("entra_token");
    if (tokenMicrosoft) {
      gravarToken(tokenMicrosoft);
      window.history.replaceState(null, "", window.location.pathname + window.location.search);
    }
    if (!lerToken()) {
      setCarregando(false);
      return;
    }
    carregarTudo()
      .catch(() => gravarToken(null))
      .finally(() => setCarregando(false));
  }, [carregarTudo]);

  useEffect(() => {
    const aoExpirar = () => {
      setUsuario(null);
      setObras([]);
    };
    window.addEventListener("treele:sessao-expirada", aoExpirar);
    return () => window.removeEventListener("treele:sessao-expirada", aoExpirar);
  }, []);

  const entrar = useCallback(
    async (email: string, senha: string, manterConectado = false) => {
      const r = await api.post<{ token: string }>("/auth/login", {
        email,
        senha,
        manter_conectado: manterConectado,
      });
      gravarToken(r.token);
      // Quem entra não herda a obra de quem usou o navegador antes.
      localStorage.removeItem(CHAVE_OBRA);
      await carregarTudo();
    },
    [carregarTudo],
  );

  const sair = useCallback(() => {
    gravarToken(null);
    localStorage.removeItem(CHAVE_OBRA);
    setUsuario(null);
    setObras([]);
  }, []);

  const recarregarObras = useCallback(async () => {
    setObras(await api.get<Obra[]>("/obras"));
  }, []);

  const valor = useMemo(
    () => ({
      usuario,
      obras,
      disciplinas,
      fases,
      carregando,
      entrar,
      sair,
      recarregarObras,
    }),
    [usuario, obras, disciplinas, fases, carregando, entrar, sair, recarregarObras],
  );

  return <Contexto.Provider value={valor}>{children}</Contexto.Provider>;
}

export function useSessao(): Sessao {
  const ctx = useContext(Contexto);
  if (!ctx) throw new Error("useSessao precisa estar dentro de ProvedorSessao.");
  return ctx;
}
