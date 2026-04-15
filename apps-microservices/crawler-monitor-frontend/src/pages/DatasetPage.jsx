import { useParams, useNavigate } from 'react-router-dom';
import DatasetAnalyzer from '../components/DatasetAnalyzer';

/**
 * Full-screen page wrapping the DatasetAnalyzer.
 * Path: /jobs/:id/dataset — replaces the previous modal opened from JobDetails.
 */
const DatasetPage = ({ token }) => {
  const { id } = useParams();
  const navigate = useNavigate();
  if (!id) return null;
  return <DatasetAnalyzer jobId={id} token={token} onClose={() => navigate(`/jobs/${id}`)} />;
};

export default DatasetPage;