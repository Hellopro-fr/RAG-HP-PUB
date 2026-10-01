import { useNavigate } from 'react-router-dom';
import CallbacksPanel from '../components/CallbacksPanel';

/**
 * Page autonome des callbacks en échec — route `/callbacks`.
 *
 * `onClose` est câblé au bouton « Retour » du panneau : il laisse au parent la
 * chance de rafraîchir son compteur, puis ramène sur la vue d'ensemble.
 */
const CallbacksPage = ({ token, onClose }) => {
  const navigate = useNavigate();
  const handleClose = () => {
    onClose?.();
    navigate('/');
  };
  return <CallbacksPanel token={token} onClose={handleClose} />;
};

export default CallbacksPage;
