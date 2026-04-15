import React from 'react';
import { AlertTriangle, RefreshCw } from 'lucide-react';

/**
 * Top-level error boundary.
 * Catches render errors in the subtree and shows a recovery UI instead of
 * a blank page. Does NOT catch async errors (use try/catch + toast for those).
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
    // Log to console — in prod we'd ship this to Sentry/Datadog
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

    return (
      <div className="min-h-screen bg-gray-900 text-gray-300 flex items-center justify-center p-4">
        <div className="bg-gray-800 border border-red-500/40 rounded-lg shadow-xl max-w-2xl w-full p-6 space-y-4">
          <div className="flex items-center gap-3">
            <AlertTriangle className="w-8 h-8 text-red-400" />
            <h2 className="text-xl font-bold text-white">Une erreur est survenue</h2>
          </div>
          <p className="text-sm text-gray-400">
            Une erreur d&apos;affichage a été interceptée. La vue actuelle ne peut pas être rendue.
          </p>
          <div className="bg-gray-900 rounded p-3 font-mono text-xs text-red-300 overflow-auto max-h-40">
            {this.state.error.message || String(this.state.error)}
          </div>
          {this.state.info && this.state.info.componentStack && (
            <details className="text-xs text-gray-500">
              <summary className="cursor-pointer">Stack trace (dev)</summary>
              <pre className="mt-2 whitespace-pre-wrap break-all">
                {this.state.info.componentStack.trim()}
              </pre>
            </details>
          )}
          <div className="flex gap-2 justify-end pt-2">
            <button
              onClick={this.handleReset}
              className="px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded text-sm"
            >
              Réessayer
            </button>
            <button
              onClick={this.handleReload}
              className="px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded text-sm text-white inline-flex items-center gap-2"
            >
              <RefreshCw className="w-4 h-4" />
              Recharger la page
            </button>
          </div>
        </div>
      </div>
    );
  }
}

export default ErrorBoundary;