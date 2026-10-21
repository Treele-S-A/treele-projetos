/** Vista do modelo 3D presa a uma reprovação (TREELE, 21/10/2026): a imagem
 *  marcada, que abre grande numa aba nova, e o link para reabrir a cena. */

import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "./api";

interface Vista {
  id: number;
  titulo: string;
  imagem_url: string | null;
}

export default function VistaAnexada({ vistaId }: { vistaId: number }) {
  const [vista, setVista] = useState<Vista | null>(null);
  const [falhou, setFalhou] = useState(false);

  useEffect(() => {
    api
      .get<Vista>(`/vistas/${vistaId}`)
      .then(setVista)
      .catch(() => setFalhou(true));
  }, [vistaId]);

  if (falhou) return null;
  return (
    <div className="vista-anexada">
      {vista?.imagem_url && (
        <a href={vista.imagem_url} target="_blank" rel="noreferrer" title="Abrir a imagem marcada">
          <img src={vista.imagem_url} alt={`Vista marcada: ${vista.titulo}`} />
        </a>
      )}
      <div>
        <span className="rotulo">Vista do modelo 3D</span>
        <div style={{ fontSize: 13, margin: "2px 0 6px" }}>{vista?.titulo ?? "…"}</div>
        <Link className="botao secundario pequeno" to={`/modelos?vista=${vistaId}`}>
          Abrir a vista no 3D
        </Link>
      </div>
    </div>
  );
}
