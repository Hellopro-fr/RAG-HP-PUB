import { useParams, useNavigate } from 'react-router-dom';
import DatasetAnalyzer from '../components/DatasetAnalyzer';

/**
 * Page autonome de l'analyseur de dataset — route `/jobs/:id/dataset`.
 *
 * DatasetAnalyzer porte son propre en-tete (titre + bouton « Retour au job »),
 * qui ramene ici sur /jobs/:id.
 */
const DatasetPage = ({ token }) => {
  const { id } = useParams();
  const navigate = useNavigate();
  if (!id) return null;
  return <DatasetAnalyzer jobId={id} token={token} onClose={() => navigate(`/jobs/${id}`)} />;
};

export default DatasetPage;