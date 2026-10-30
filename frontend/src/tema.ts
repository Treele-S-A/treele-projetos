import { useEffect, useState } from "react";

export type Tema = "claro" | "escuro";
const CHAVE = "treele.projetos.tema";

export function lerTema(): Tema {
  return localStorage.getItem(CHAVE) === "escuro" ? "escuro" : "claro";
}

export function aplicarTema(tema: Tema) {
  localStorage.setItem(CHAVE, tema);
  document.documentElement.dataset.tema = tema;
  window.dispatchEvent(new Event("treele:tema"));
}

export function useTema(): [Tema, (tema: Tema) => void] {
  const [tema, setTema] = useState<Tema>(lerTema);
  useEffect(() => {
    document.documentElement.dataset.tema = lerTema();
    const atualizar = () => setTema(lerTema());
    window.addEventListener("treele:tema", atualizar);
    return () => window.removeEventListener("treele:tema", atualizar);
  }, []);
  return [tema, aplicarTema];
}
