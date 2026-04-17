// src/components/DatasetAnalyzer.jsx
import { Server, XCircle } from 'lucide-react';
import DuplicatesTab from './DuplicatesTab';

/**
 * Dataset page shell.
 * After Task 8 this becomes a tabbed container (Succès/Erreurs/Non-FR/Doublons).
 * For now it renders only the extracted DuplicatesTab — behavior unchanged
 * vs. the legacy monolithic version.
 */
const DatasetAnalyzer = ({ jobId, onClose, token }) => (
  <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-50 p-4">
    <div className="bg-gray-800 rounded-lg shadow-xl w-full max-w-2xl overflow-hidden">
      <div className="flex justify-between items-center p-4 border-b border-gray-700 bg-gray-750">
        <h3 className="text-xl font-bold text-white flex items-center gap-2">
          <Server className="w-5 h-5 text-purple-400" /> Analyse Dataset
        </h3>
        <button onClick={onClose} className="text-gray-400 hover:text-white">
          <XCircle className="w-6 h-6" />
        </button>
      </div>
      <div className="p-6">
        <DuplicatesTab jobId={jobId} token={token} />
      </div>
    </div>
  </div>
);

export default DatasetAnalyzer;
