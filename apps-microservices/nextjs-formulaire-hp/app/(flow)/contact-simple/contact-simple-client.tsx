"use client";

import { useFlowNavigation } from '@/hooks/useFlowNavigation';
import ContactFormSimple from '@/components/flow/ContactFormSimple';

export default function ContactSimpleClient() {
  const { goToSomethingToAdd } = useFlowNavigation();

  return (
    <ContactFormSimple
      onBack={goToSomethingToAdd}
    />
  );
}
