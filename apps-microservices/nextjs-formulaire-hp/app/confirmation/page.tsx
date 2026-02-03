import type { Metadata } from 'next';
import Link from 'next/link';

export const metadata: Metadata = {
  title: 'Confirmation - Demande envoyée',
  description: 'Votre demande de devis a été envoyée avec succès.',
};

export default function ConfirmationPage() {
  return (
    <div className="min-h-screen flex flex-col items-center justify-center p-8">
      <div className="max-w-md mx-auto text-center space-y-6">
        {/* Icône de succès */}
        <div className="w-20 h-20 mx-auto bg-success/10 rounded-full flex items-center justify-center">
          <svg
            className="w-10 h-10 text-success"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M5 13l4 4L19 7"
            />
          </svg>
        </div>

        <h1 className="text-3xl font-bold text-foreground">
          Demande envoyée !
        </h1>

        <p className="text-muted-foreground">
          Votre demande de devis a été transmise aux fournisseurs sélectionnés.
          Vous recevrez leurs réponses par email dans les prochaines 24 à 48 heures.
        </p>

        <div className="bg-card border rounded-lg p-6 text-left space-y-4">
          <h2 className="font-semibold text-foreground">Prochaines étapes</h2>
          <ul className="space-y-2 text-sm text-muted-foreground">
            <li className="flex items-start gap-2">
              <span className="text-primary">1.</span>
              <span>Les fournisseurs examinent votre demande</span>
            </li>
            <li className="flex items-start gap-2">
              <span className="text-primary">2.</span>
              <span>Vous recevez les devis par email</span>
            </li>
            <li className="flex items-start gap-2">
              <span className="text-primary">3.</span>
              <span>Comparez et choisissez l'offre qui vous convient</span>
            </li>
          </ul>
        </div>

        <div className="pt-4">
          <Link
            href="/"
            className="inline-flex items-center justify-center rounded-md bg-primary px-6 py-3 text-sm font-medium text-primary-foreground shadow transition-colors hover:bg-primary/90 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
          >
            Retour à l'accueil
          </Link>
        </div>
      </div>
    </div>
  );
}
