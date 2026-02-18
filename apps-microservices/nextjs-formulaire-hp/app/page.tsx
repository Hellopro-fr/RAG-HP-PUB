import { Suspense } from 'react';
import type { Metadata } from 'next';
import QuestionnaireClient from './(flow)/questionnaire/questionnaire-client';

export const metadata: Metadata = {
  title: 'Questionnaire - Définissez vos besoins',
  description: 'Répondez à quelques questions pour nous aider à trouver les fournisseurs adaptés à vos besoins.',
};

// Type pour les paramètres d'URL (Next.js 15)
interface PageProps {
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>;
}

export default async function Home({ searchParams }: PageProps) {
  // Récupérer les searchParams du middleware rewrite
  const params = await searchParams;
  // categoryId vient du token validé par le middleware
  // id_categorie vient du mode dev bypass
  const categoryId = params.categoryId || params.id_categorie;
  // urlData contient les données pré-remplies (réponse Q1) si présentes dans le token
  const urlData = params.urlData;
  // token original pour la redirection après F5
  const token = params.token;
  // token original pour la redirection après F5
  const ddc = params.ddc;

  return (
    <Suspense fallback={null}>
      <QuestionnaireClient
        initialCategoryId={typeof categoryId === 'string' ? categoryId : undefined}
        initialUrlData={typeof urlData === 'string' ? urlData : undefined}
        initialToken={typeof token === 'string' ? token : undefined}
        initialDdc={typeof ddc === 'string' ? ddc : undefined}
      />
    </Suspense>
  );
}
