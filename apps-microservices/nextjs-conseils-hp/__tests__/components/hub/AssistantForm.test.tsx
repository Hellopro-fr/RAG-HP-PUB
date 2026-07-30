import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { AssistantForm, openAssistantDialog } from '@/components/hub/AssistantForm';
import { listHubPages } from '@/data/hub';

const data = listHubPages()[0].assistant;

describe('AssistantForm', () => {
  it('rend l’étape 1 inline dans le hero, sans clic', () => {
    render(<AssistantForm data={data} />);
    expect(screen.getByText(data.cardTitle)).toBeDefined();
    expect(screen.getByText(data.steps[0].label)).toBeDefined();
    for (const option of data.steps[0].options) {
      expect(screen.getByText(option)).toBeDefined();
    }
  });

  it('désactive le bouton de démarrage tant qu’aucune réponse n’est choisie', () => {
    render(<AssistantForm data={data} />);
    expect(screen.getByRole('button', { name: new RegExp(data.ctaLabel, 'i') })).toBeDisabled();
  });

  it('ouvre le dialog sur l’étape 2 après un choix unique', async () => {
    render(<AssistantForm data={data} />);
    fireEvent.click(screen.getByText(data.steps[0].options[0]));
    await waitFor(() => {
      expect(screen.getByRole('dialog')).toBeDefined();
    });
    expect(screen.getByText(data.steps[1].label)).toBeDefined();
  });

  it('marque l’option choisie comme sélectionnée', () => {
    render(<AssistantForm data={data} />);
    const option = screen.getByText(data.steps[0].options[1]).closest('button');
    fireEvent.click(option!);
    expect(option).toHaveAttribute('aria-pressed', 'true');
  });

  it('s’ouvre sur l’événement window hp:open-assistant-dialog', async () => {
    render(<AssistantForm data={data} />);
    expect(screen.queryByRole('dialog')).toBeNull();
    openAssistantDialog();
    await waitFor(() => {
      expect(screen.getByRole('dialog')).toBeDefined();
    });
  });

  it('n’avance pas automatiquement sur une étape à choix multiple', async () => {
    const multiFirst = {
      ...data,
      steps: [{ ...data.steps[2] }, ...data.steps.slice(0, 2)],
    };
    render(<AssistantForm data={multiFirst} />);
    fireEvent.click(screen.getByText(multiFirst.steps[0].options[0]));
    // Laisse passer le délai d'auto-avance des choix uniques (180 ms).
    await new Promise((resolve) => setTimeout(resolve, 250));
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  /**
   * POC : la soumission ne transmet rien. Ce test verrouille le comportement
   * attendu aujourd'hui — il devra être RÉÉCRIT quand le branchement réel
   * arrivera, et c'est précisément le signal qu'on veut.
   */
  it('affiche la confirmation sans aucun appel réseau', async () => {
    const fetchCalls: unknown[] = [];
    const originalFetch = globalThis.fetch;
    globalThis.fetch = ((...args: unknown[]) => {
      fetchCalls.push(args);
      return Promise.reject(new Error('aucun appel réseau attendu'));
    }) as typeof fetch;

    try {
      // Un seul écran de questions, pour atteindre l'étape e-mail rapidement.
      const short = { ...data, steps: [data.steps[0]] };
      render(<AssistantForm data={short} />);
      fireEvent.click(screen.getByText(short.steps[0].options[0]));

      await waitFor(() => {
        expect(screen.getByLabelText(short.contact.label)).toBeDefined();
      });

      fireEvent.change(screen.getByLabelText(short.contact.label), {
        target: { value: 'erick@hellopro.fr' },
      });
      fireEvent.click(screen.getByRole('button', { name: new RegExp(short.contact.submitLabel, 'i') }));

      await waitFor(() => {
        expect(screen.getByText(short.success.title)).toBeDefined();
      });
      expect(fetchCalls).toHaveLength(0);
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  it('refuse une adresse e-mail invalide', async () => {
    const short = { ...data, steps: [data.steps[0]] };
    render(<AssistantForm data={short} />);
    fireEvent.click(screen.getByText(short.steps[0].options[0]));

    await waitFor(() => {
      expect(screen.getByLabelText(short.contact.label)).toBeDefined();
    });

    fireEvent.change(screen.getByLabelText(short.contact.label), {
      target: { value: 'pas-un-email' },
    });
    expect(
      screen.getByRole('button', { name: new RegExp(short.contact.submitLabel, 'i') })
    ).toBeDisabled();
  });
});
