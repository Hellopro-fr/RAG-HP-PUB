import { useParams, useNavigate } from 'react-router-dom';
import RequestQueueEditor from '../components/RequestQueueEditor';

/**
 * Page autonome de l'editeur de request queue — route `/jobs/:id/queue`.
 *
 * Ce n'est pas une sous-vue de la vue d'ensemble : la page se monte seule dans
 * le <main> de l'AppShell. RequestQueueEditor porte son propre en-tete (titre +
 * bouton « Retour au job »), qui ramene ici sur /jobs/:id.
 */
const QueuePage = ({ token }) => {
  const { id } = useParams();
  const navigate = useNavigate();
  if (!id) return null;
  return <RequestQueueEditor jobId={id} token={token} onClose={() => navigate(`/jobs/${id}`)} />;
};

export default QueuePage;