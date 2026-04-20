import { useState, useEffect, useRef } from 'react';
import {
  Code, RefreshCw, Search, Trash2, Filter,
  ChevronLeft, ChevronRight, AlignLeft, CheckCircle, AlertCircle, X, ArrowLeft,
} from 'lucide-react';
import Editor from 'react-simple-code-editor';
import Prism from 'prismjs';
import 'prismjs/components/prism-json';
import { api } from '../lib/api';
import ConfirmDestructive from './ConfirmDestructive';
import { Card } from './ui/card';
import { Input } from './ui/input';
import { Button } from './ui/button';
import { cn } from '../lib/utils';

const STATUS_OPTIONS = [
  { id: 'all',     label: 'Tous' },
  { id: 'handled', label: '✓ Traités' },
  { id: 'pending', label: '○ En attente' },
];

const RequestQueueEditor = ({ jobId, onClose, token }) => {
  const [files, setFiles] = useState([]);
  const [selectedFile, setSelectedFile] = useState(null);
  const [content, setContent] = useState('');
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [repairing, setRepairing] = useState(false);
  const [error, setError] = useState(null);
  const [successMsg, setSuccessMsg] = useState(null);
  const [searchTerm, setSearchTerm] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');

  const [statusFilter, setStatusFilter] = useState('all');
  const [counts, setCounts] = useState(null);

  const [page, setPage] = useState(1);
  const [limit] = useState(50);
  const [totalPages, setTotalPages] = useState(1);
  const [totalItems, setTotalItems] = useState(0);

  useEffect(() => {
    const id = setTimeout(() => setDebouncedSearch(searchTerm), 300);
    return () => clearTimeout(id);
  }, [searchTerm]);

  useEffect(() => {
    fetchFiles();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobId, page, debouncedSearch, statusFilter]);

  // Reset scroll de la liste à chaque changement de filtre/page/search :
  // sinon on reste scrollé sur d'anciens résultats et on croit que la requête
  // n'a rien retourné.
  const listRef = useRef(null);
  useEffect(() => {
    if (listRef.current) listRef.current.scrollTop = 0;
  }, [debouncedSearch, statusFilter, page]);

  const fetchFiles = async () => {
    setLoading(true);
    try {
      const data = await api.get(
        `/jobs/${jobId}/request-queues`,
        token,
        { query: {
            page: String(page),
            limit: String(limit),
            search: debouncedSearch,
            status: statusFilter,
          } }
      );

      if (data.items) {
        setFiles(data.items);
        setTotalPages(data.totalPages);
        setTotalItems(data.total);
        if (data.counts) setCounts(data.counts);
      } else {
        setFiles(Array.isArray(data) ? data : []);
        setTotalPages(1);
        setTotalItems(Array.isArray(data) ? data.length : 0);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const loadFile = async (file) => {
    setLoading(true);
    setSelectedFile(file);
    setError(null);
    setSuccessMsg(null);
    try {
      const data = await api.get(`/jobs/${jobId}/request-queues/${file.domain}/${file.name}`, token);
      try {
        setContent(JSON.stringify(data, null, 2));
      } catch {
        setContent(typeof data === 'string' ? data : String(data));
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const formatJson = () => {
    try {
      const parsed = JSON.parse(content);
      setContent(JSON.stringify(parsed, null, 2));
      setError(null);
    } catch (e) {
      setError('JSON Invalide: ' + e.message);
    }
  };

  const saveFile = async () => {
    if (!selectedFile) return;
    setSaving(true);
    setError(null);
    setSuccessMsg(null);
    try {
      let jsonContent;
      try {
        jsonContent = JSON.parse(content);
      } catch (e) {
        throw new Error('JSON Invalide: ' + e.message);
      }

      await api.post(
        `/jobs/${jobId}/request-queues/${selectedFile.domain}/${selectedFile.name}`,
        token,
        jsonContent
      );

      setSuccessMsg('Fichier sauvegardé avec succès !');
      fetchFiles();
    } catch (err) {
      setError(`Erreur: ${err.message}`);
    } finally {
      setSaving(false);
    }
  };

  const [queueAnalysis, setQueueAnalysis] = useState(null);
  const [analyzing, setAnalyzing] = useState(false);

  const analyzeQueue = async () => {
    setAnalyzing(true);
    setError(null);
    setSuccessMsg(null);
    try {
      const data = await api.get(`/jobs/${jobId}/request-queues/analyze`, token);
      setQueueAnalysis(data);
      setSuccessMsg(`Analyse terminée : ${data.total} URLs analysées`);
    } catch (err) {
      setError(`Erreur lors de l'analyse : ${err.message}`);
    } finally {
      setAnalyzing(false);
    }
  };

  const cleanPatterns = async () => {
    if (!window.confirm('Êtes-vous sûr de vouloir nettoyer les patterns ? Cela supprimera les URLs correspondant aux filtres (login, cart, facebook, etc.).')) {
      return;
    }

    setRepairing(true);
    setError(null);
    setSuccessMsg(null);
    try {
      const data = await api.post(`/jobs/${jobId}/request-queues/clean-patterns`, token);
      setSuccessMsg(`Nettoyage patterns terminé : ${data.deleted} fichiers supprimés sur ${data.scanned} scannés.`);
      setQueueAnalysis(null);
      fetchFiles();
    } catch (err) {
      setError(`Erreur lors du nettoyage patterns : ${err.message}`);
    } finally {
      setRepairing(false);
    }
  };

  const [showDropConfirm, setShowDropConfirm] = useState(false);

  const performDrop = async () => {
    setRepairing(true);
    setError(null);
    setSuccessMsg(null);
    try {
      await api.post(`/jobs/${jobId}/request-queues/drop`, token);
      setSuccessMsg(`Queue entièrement vidée avec succès !`);
      fetchFiles();
      setQueueAnalysis(null);
      setShowDropConfirm(false);
    } catch (err) {
      setError(`Erreur lors du "Drop" : ${err.message}`);
    } finally {
      setRepairing(false);
    }
  };

  const dropQueue = () => setShowDropConfirm(true);

  const handleSearchChange = (e) => {
    setSearchTerm(e.target.value);
    setPage(1);
  };

  const changeStatusFilter = (next) => {
    setStatusFilter(next);
    setPage(1);
  };

  return (
    <div className="p-4">
      <style>{`
        .queue-json-editor .token.property    { color: hsl(var(--info)); }
        .queue-json-editor .token.string      { color: hsl(var(--success)); }
        .queue-json-editor .token.number      { color: hsl(var(--warning)); }
        .queue-json-editor .token.boolean,
        .queue-json-editor .token.null        { color: hsl(var(--primary)); }
        .queue-json-editor .token.punctuation { color: hsl(var(--muted-foreground)); }
        .queue-json-editor .token.operator    { color: hsl(var(--muted-foreground)); }
        .queue-json-editor textarea,
        .queue-json-editor pre {
          white-space: pre !important;
          overflow-wrap: normal !important;
          word-break: normal !important;
          color: hsl(var(--foreground));
          background: transparent !important;
        }
        .queue-json-editor > div {
          min-width: max-content !important;
          overflow: visible !important;
        }
      `}</style>
      <ConfirmDestructive
        open={showDropConfirm}
        title="Drop entire queue"
        description={
          <>
            Cela va supprimer <strong>{totalItems}</strong> requête{totalItems > 1 ? 's' : ''} en attente
            pour le job <code className="rounded bg-muted px-1 py-0.5 text-warning">{jobId}</code>.
            <br /><br />
            Le crawler repartira de zéro (l&apos;historique des URLs déjà visitées est conservé).
            Cette action est <strong>irréversible</strong> pour la queue actuelle.
          </>
        }
        shortId={String(jobId).slice(0, 8)}
        onConfirm={performDrop}
        onCancel={() => setShowDropConfirm(false)}
        busy={repairing}
      />

      <Card className="flex h-[calc(100vh-6rem)] flex-col overflow-hidden">
        <div className="flex items-center justify-between border-b border-border p-4">
          <h3 className="flex items-center gap-2 text-base font-semibold">
            <Code className="h-4 w-4 text-primary" />
            Éditeur Request Queue
            <span className="font-mono text-xs font-normal text-muted-foreground">
              #{String(jobId).slice(0, 10)}
            </span>
          </h3>
          {onClose && (
            <Button variant="outline" size="sm" onClick={onClose}>
              <ArrowLeft className="h-4 w-4" />
              Retour au job
            </Button>
          )}
        </div>

        <div className="flex flex-1 overflow-hidden">
          {/* Left panel */}
          <div className="flex w-1/3 flex-col border-r border-border bg-card">
            <div className="space-y-3 border-b border-border bg-muted/30 p-3">
              {counts && (
                <div className="flex items-center gap-3 rounded-md border border-border bg-background px-3 py-2 text-xs">
                  <span className="text-muted-foreground">Total</span>
                  <span className="font-mono font-semibold text-foreground">{counts.total.toLocaleString('fr-FR')}</span>
                  <span className="text-muted-foreground/50">·</span>
                  <span className="text-muted-foreground">✓ Traités</span>
                  <span className="font-mono font-semibold text-success">{counts.handled.toLocaleString('fr-FR')}</span>
                  <span className="text-muted-foreground/50">·</span>
                  <span className="text-muted-foreground">○ En attente</span>
                  <span className="font-mono font-semibold text-warning">{counts.pending.toLocaleString('fr-FR')}</span>
                </div>
              )}

              <div className="flex gap-0.5 rounded-md border border-border bg-background p-0.5">
                {STATUS_OPTIONS.map(opt => (
                  <button
                    key={opt.id}
                    type="button"
                    onClick={() => changeStatusFilter(opt.id)}
                    className={cn(
                      'flex-1 rounded px-3 py-1 text-xs transition-colors',
                      statusFilter === opt.id
                        ? 'bg-primary text-primary-foreground'
                        : 'text-muted-foreground hover:bg-accent hover:text-foreground'
                    )}
                  >
                    {opt.label}
                  </button>
                ))}
              </div>

              <div className="flex items-center justify-between">
                <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  Queue ({totalItems})
                </h4>
                <div className="flex gap-2">
                  {!queueAnalysis && (
                    <Button
                      size="sm"
                      className="h-7"
                      onClick={analyzeQueue}
                      disabled={analyzing}
                      title="Analyser la composition de la queue"
                    >
                      {analyzing ? <RefreshCw className="h-3 w-3 animate-spin" /> : <Search className="h-3 w-3" />}
                      Analyser
                    </Button>
                  )}
                </div>
              </div>

              {queueAnalysis && (
                <div className="space-y-2 rounded-md border border-border bg-background p-3 text-xs animate-in fade-in slide-in-from-top-2">
                  <div className="mb-1 flex items-center justify-between font-semibold text-foreground">
                    <span>Résultat Analyse</span>
                    <button
                      onClick={() => setQueueAnalysis(null)}
                      className="text-muted-foreground hover:text-foreground"
                      title="Fermer"
                    >
                      <X className="h-3 w-3" />
                    </button>
                  </div>

                  <div className="grid grid-cols-2 gap-2">
                    <div className="rounded border border-destructive/30 bg-destructive/10 p-1.5">
                      <span className="block text-destructive">Bloquées</span>
                      <span className="font-mono font-bold text-foreground">{queueAnalysis.blocked}</span>
                    </div>
                    <div className="rounded border border-success/30 bg-success/10 p-1.5">
                      <span className="block text-success">Valides</span>
                      <span className="font-mono font-bold text-foreground">{queueAnalysis.valid}</span>
                    </div>
                  </div>

                  <div className="flex h-1.5 w-full overflow-hidden rounded-full bg-muted">
                    <div style={{ width: `${queueAnalysis.blockedPercent}%` }} className="h-full bg-destructive" />
                    <div style={{ width: `${queueAnalysis.validPercent}%` }}   className="h-full bg-success" />
                  </div>

                  <div className="flex gap-2 pt-1">
                    <Button
                      variant="destructive"
                      size="sm"
                      className="h-8 flex-1"
                      onClick={dropQueue}
                      title="Supprimer TOUTES les URLs (Valides et Bloquées)"
                    >
                      <Trash2 className="h-3 w-3" /> Tout Supprimer
                    </Button>

                    {queueAnalysis.blocked > 0 && (
                      <Button
                        size="sm"
                        className="h-8 flex-1 bg-warning text-warning-foreground hover:bg-warning/90"
                        onClick={cleanPatterns}
                        title="Supprimer uniquement les URLs bloquées"
                      >
                        <Filter className="h-3 w-3" /> Nettoyer ({queueAnalysis.blocked})
                      </Button>
                    )}
                  </div>
                </div>
              )}

              <Input
                type="text"
                placeholder="Rechercher URL…"
                className="h-8 text-xs"
                value={searchTerm}
                onChange={handleSearchChange}
              />
            </div>

            <div ref={listRef} className="flex-1 space-y-1 overflow-y-auto p-2">
              {loading && !selectedFile && (
                <div className="p-4 text-center">
                  <RefreshCw className="mx-auto h-5 w-5 animate-spin text-muted-foreground" />
                </div>
              )}
              {files.length === 0 && !loading && (
                <div className="p-4 text-center text-xs text-muted-foreground">Aucune requête trouvée</div>
              )}
              {files.map(file => (
                <button
                  key={file.path}
                  onClick={() => loadFile(file)}
                  className={cn(
                    'group w-full truncate rounded-md px-3 py-2 text-left text-sm transition-colors',
                    selectedFile?.path === file.path
                      ? 'bg-primary text-primary-foreground'
                      : 'text-foreground hover:bg-accent'
                  )}
                >
                  <div className="flex items-center gap-2 truncate font-medium" title={file.url || file.name}>
                    <span
                      className={cn(
                        'shrink-0',
                        file.isHandled
                          ? 'text-success'
                          : selectedFile?.path === file.path ? 'text-primary-foreground/60' : 'text-muted-foreground'
                      )}
                      title={file.isHandled ? 'Traité' : 'En attente'}
                      aria-label={file.isHandled ? 'Traité' : 'En attente'}
                    >
                      {file.isHandled ? '✓' : '○'}
                    </span>
                    <span className="truncate">{file.url || file.name}</span>
                  </div>
                  <div className="mt-1 flex items-center justify-between">
                    <span className={cn(
                      'rounded px-1.5 py-0.5 text-[10px]',
                      file.method === 'GET' ? 'bg-success/15 text-success' : 'bg-warning/15 text-warning'
                    )}>
                      {file.method || 'UNK'}
                    </span>
                    <span className="text-xs opacity-70">{file.retryCount || 0} retries</span>
                  </div>
                </button>
              ))}
            </div>

            <div className="flex items-center justify-between border-t border-border bg-muted/30 p-2">
              <Button
                variant="ghost"
                size="icon"
                className="h-7 w-7"
                onClick={() => setPage(p => Math.max(1, p - 1))}
                disabled={page === 1 || loading}
              >
                <ChevronLeft className="h-4 w-4" />
              </Button>
              <span className="font-mono text-xs text-muted-foreground">
                {page} / {totalPages}
              </span>
              <Button
                variant="ghost"
                size="icon"
                className="h-7 w-7"
                onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                disabled={page === totalPages || loading}
              >
                <ChevronRight className="h-4 w-4" />
              </Button>
            </div>
          </div>

          {/* Editor area */}
          <div className="flex min-w-0 flex-1 flex-col overflow-hidden bg-background">
            {selectedFile ? (
              <>
                <div className="flex items-center justify-between gap-2 border-b border-border bg-card p-2">
                  <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
                    <span className="truncate font-mono text-xs text-muted-foreground">{selectedFile.path}</span>
                    <span className="truncate text-sm font-semibold text-foreground" title={selectedFile.url}>
                      {selectedFile.url}
                    </span>
                  </div>
                  <div className="flex shrink-0 gap-2">
                    <Button variant="outline" size="sm" onClick={formatJson} title="Formater le JSON">
                      <AlignLeft className="h-4 w-4" />
                      Formater
                    </Button>
                    <Button
                      size="sm"
                      onClick={saveFile}
                      disabled={saving}
                      className="bg-success text-success-foreground hover:bg-success/90"
                    >
                      {saving ? <RefreshCw className="h-4 w-4 animate-spin" /> : <CheckCircle className="h-4 w-4" />}
                      Sauvegarder
                    </Button>
                  </div>
                </div>

                {error && (
                  <div className="flex items-center gap-2 border-b border-destructive/40 bg-destructive/10 p-2 text-sm text-destructive">
                    <AlertCircle className="h-4 w-4" /> {error}
                  </div>
                )}
                {successMsg && (
                  <div className="flex items-center gap-2 border-b border-success/40 bg-success/10 p-2 text-sm text-success">
                    <CheckCircle className="h-4 w-4" /> {successMsg}
                  </div>
                )}

                <div className="queue-json-editor flex-1 overflow-auto bg-background">
                  <Editor
                    value={content}
                    onValueChange={setContent}
                    highlight={code => Prism.highlight(code, Prism.languages.json, 'json')}
                    padding={16}
                    textareaClassName="focus:outline-none"
                    preClassName=""
                    style={{
                      fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Consolas, monospace',
                      fontSize: 13,
                      minHeight: '100%',
                    }}
                  />
                </div>
              </>
            ) : (
              <div className="flex flex-1 items-center justify-center text-sm text-muted-foreground">
                Sélectionnez une requête pour l&apos;éditer
              </div>
            )}
          </div>
        </div>
      </Card>
    </div>
  );
};

export default RequestQueueEditor;
