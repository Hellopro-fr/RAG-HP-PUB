import { useNavigate } from 'react-router-dom';
import CallbacksPanel from '../components/CallbacksPanel';

/**
 * Full-screen page wrapping the CallbacksPanel.
 * Path: /callbacks
 *
 * Replaces the modal previously toggled from a header badge button.
 * Closing the page navigates back to / (Overview).
 */
const CallbacksPage = ({ token, onClose }) => {
  const navigate = useNavigate();
  const handleClose = () => {
    if (onClose) onClose(); // give parent a chance to refresh count
    navigate('/');
  };
  return <CallbacksPanel token={token} onClose={handleClose} />;
};

export default CallbacksPage;