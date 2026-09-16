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

interface Sessao {
  usuario: Usuario | null;
  obras: Obra[];
  disciplinas: Catalogo[];
  fases: Catalogo[];
  carregando: boolean;
  entrar(email: string, senha: string): Promise<void>;
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
    async (email: string, senha: string) => {
      const r = await api.post<{ token: string }>("/auth/login", { email, senha });
      gravarToken(r.token);
      await carregarTudo();
    },
    [carregarTudo],
  );

  const sair = useCallback(() => {
    gravarToken(null);
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
