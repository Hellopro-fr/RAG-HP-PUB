import React from 'react';
import { AlertTriangle, RefreshCw } from 'lucide-react';
import { tryAutoReloadOnStaleChunk, hasAlreadyTriedReload } from '../lib/staleChunk';

/**
 * Top-level error boundary.
 * Catches render errors in the subtree and shows a recovery UI instead of
 * a blank page. Does NOT catch async errors (use try/catch + toast for those).
 *
 * Kept as a plain class component (not shadcn primitives) because it runs
 * BEFORE ThemeProvider mounts -- reads theme variables directly via CSS vars,
 * so both light and dark render correctly as long as :root tokens are defined.
 *
 * Stale-chunk recovery: si l'erreur correspond a un import() de chunk echoue
 * apres un redeploiement, la page est rechargee automatiquement une fois pour
 * recuperer le nouvel index.html. Un flag sessionStorage evite la boucle infinie.
 */
class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { error: null, info: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, info) {
    // Tenter un rechargement automatique si c'est un chunk perime apres deploiement.
    // tryAutoReloadOnStaleChunk() ne recharge que si le flag n'est pas deja pose.
    if (tryAutoReloadOnStaleChunk(error)) {
      // Le rechargement est en cours (setTimeout 100ms) -- ne pas loguer d'erreur
      return;
    }
    console.error('[ErrorBoundary] Caught render error:', error, info);
    this.setState({ info });
  }

  handleReset = () => {
    this.setState({ error: null, info: null });
  };

  handleReload = () => {
    window.location.reload();
  };

  render() {
    if (!this.state.error) return this.props.children;

    // Detecter si on a deja tente un rechargement automatique dans cette session.
    // Si oui, afficher un message plus explicite invitant au rechargement force.
    const alreadyTried = hasAlreadyTriedReload();

    return (
      <div className="flex min-h-screen items-center justify-center bg-bg-1 p-4 text-ink-0">
        <div className="w-full max-w-2xl space-y-4 rounded-lg border border-err/40 bg-surface p-6 shadow-xl">
          <div className="flex items-center gap-3">
            <AlertTriangle className="h-7 w-7 text-err" />
            <h2 className="text-xl font-bold">
              {alreadyTried
                ? "Mise à jour de l'application requise"
                : 'Une erreur est survenue'}
            </h2>
          </div>
          <p className="text-sm text-ink-3">
            {alreadyTried ? (
              <>
                L&apos;application n&apos;a pas pu se mettre à jour automatiquement après un
                déploiement récent. Recharge manuellement avec{' '}
                <strong>Ctrl+Shift+R</strong> (ou <strong>⌘+Shift+R</strong> sur Mac), ou
                contacte le support si le problème persiste.
              </>
            ) : (
              "Une erreur d'affichage a été interceptée. La vue actuelle ne peut pas être rendue."
            )}
          </p>
          <div className="max-h-40 overflow-auto rounded-md border border-err/30 bg-err-soft p-3 font-mono text-xs text-err">
            {this.state.error.message || String(this.state.error)}
          </div>
          {this.state.info && this.state.info.componentStack && (
            <details className="text-xs text-ink-3">
              <summary className="cursor-pointer">Stack trace (dev)</summary>
              <pre className="mt-2 whitespace-pre-wrap break-all font-mono">
                {this.state.info.componentStack.trim()}
              </pre>
            </details>
          )}
          <div className="flex justify-end gap-2 pt-2">
            {!alreadyTried && (
              <button
                onClick={this.handleReset}
                className="inline-flex h-9 items-center rounded-md border border-hairline bg-bg-1 px-4 text-sm hover:bg-bg-2 hover:text-ink-0"
              >
                Réessayer
              </button>
            )}
            <button
              onClick={this.handleReload}
              className="inline-flex h-9 items-center gap-2 rounded-md bg-accent px-4 text-sm font-medium text-accent-foreground hover:bg-accent/90"
            >
              <RefreshCw className="h-4 w-4" />
              Recharger la page
            </button>
          </div>
        </div>
      </div>
    );
  }
}

export default ErrorBoundary;
