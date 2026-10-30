import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import { ProvedorSessao } from "./sessao";
import "./estilos.css";
// Por cima do estilos.css: a linguagem dos painéis da treèle (01/10/2026).
import "./tema-painel.css";
import "./rh-visual.css";
import "./tema-escuro.css";
import { lerTema } from "./tema";

document.documentElement.dataset.tema = lerTema();

createRoot(document.getElementById("raiz")!).render(
  <StrictMode>
    <BrowserRouter>
      <ProvedorSessao>
        <App />
      </ProvedorSessao>
    </BrowserRouter>
  </StrictMode>,
);
