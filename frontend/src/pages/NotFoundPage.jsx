import { Link } from "react-router-dom";
import { EmptyState } from "../components/ui";

export default function NotFoundPage() {
  return (
    <EmptyState icon="info" title="Página no encontrada" action={<Link className="btn btn-primary" to="/panel">Ir al panel</Link>}>
      La dirección que abriste no existe o no tienes permiso para verla.
    </EmptyState>
  );
}
