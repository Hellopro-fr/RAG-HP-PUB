import Link from 'next/link';

export default function Home() {
  return (
    <main className="min-h-screen flex flex-col items-center justify-center p-8">
      <div className="max-w-2xl mx-auto text-center space-y-8">
        <h1 className="text-4xl font-bold text-foreground">
          Trouvez votre fournisseur
        </h1>
        <p className="text-xl text-muted-foreground">
          Plateforme de mise en relation avec des fournisseurs de ponts élévateurs.
          Trouvez le fournisseur adapté à vos besoins en quelques clics.
        </p>

        <div className="flex flex-col sm:flex-row gap-4 justify-center">
          <Link
            href="/questionnaire"
            className="inline-flex items-center justify-center rounded-md bg-primary px-8 py-4 text-lg font-medium text-primary-foreground shadow transition-colors hover:bg-primary/90 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
          >
            Commencer
          </Link>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mt-12">
          <div className="p-6 rounded-lg border bg-card">
            <div className="text-3xl mb-4">1</div>
            <h3 className="font-semibold mb-2">Questionnaire</h3>
            <p className="text-sm text-muted-foreground">
              Répondez à quelques questions pour définir vos besoins
            </p>
          </div>

          <div className="p-6 rounded-lg border bg-card">
            <div className="text-3xl mb-4">2</div>
            <h3 className="font-semibold mb-2">Profil</h3>
            <p className="text-sm text-muted-foreground">
              Renseignez vos informations professionnelles
            </p>
          </div>

          <div className="p-6 rounded-lg border bg-card">
            <div className="text-3xl mb-4">3</div>
            <h3 className="font-semibold mb-2">Sélection</h3>
            <p className="text-sm text-muted-foreground">
              Choisissez parmi les fournisseurs recommandés
            </p>
          </div>
        </div>
      </div>
    </main>
  );
}
