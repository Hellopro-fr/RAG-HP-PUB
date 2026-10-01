import { Suspense } from 'react';
import type { Metadata } from 'next';
import BudgetClient from './budget-client';

export const metadata: Metadata = {
  title: 'Budget - Estimation et choix',
  description: 'Consultez l\'estimatif de prix et indiquez votre budget pour personnaliser la sélection.',
};

export default function BudgetPage() {
  return (
    <Suspense fallback={null}>
      <BudgetClient />
    </Suspense>
  );
}
