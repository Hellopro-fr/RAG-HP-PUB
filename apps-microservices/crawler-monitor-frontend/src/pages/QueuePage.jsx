import { useParams, useNavigate } from 'react-router-dom';
import RequestQueueEditor from '../components/RequestQueueEditor';

/**
 * Full-screen page wrapping the RequestQueueEditor.
 * Path: /jobs/:id/queue — replaces the previous modal that opened from JobDetails.
 *
 * The editor component is rendered as-is (it already covers the viewport),
 * and onClose navigates back to the parent /jobs/:id.
 */
const QueuePage = ({ token }) => {
  const { id } = useParams();
  const navigate = useNavigate();
  if (!id) return null;
  return <RequestQueueEditor jobId={id} token={token} onClose={() => navigate(`/jobs/${id}`)} />;
};

export default QueuePage;