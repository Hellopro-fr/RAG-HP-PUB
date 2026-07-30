import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { GuideDownloadDialog, openGuideDialog } from '@/components/hub/GuideDownloadDialog';
import { listHubPages } from '@/data/hub';

const data = listHubPages()[0].guideDialog;

/** Ouvre le dialog et attend son rendu (Radix le monte dans un portail). */
async function open() {
  openGuideDialog();
  await waitFor(() => expect(screen.getByRole('dialog')).toBeDefined());
}

describe('GuideDownloadDialog', () => {
  it('reste fermé au montage', () => {
    render(<GuideDownloadDialog data={data} />);
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('s’ouvre sur l’événement window hp:open-guide-dialog', async () => {
    render(<GuideDownloadDialog data={data} />);
    await open();
    expect(screen.getByLabelText(data.fields.email)).toBeDefined();
  });

  it('expose les 4 champs avec un nom accessible', async () => {
    render(<GuideDownloadDialog data={data} />);
    await open();
    expect(screen.getByLabelText(data.fields.name)).toBeDefined();
    expect(screen.getByLabelText(data.fields.email)).toBeDefined();
    expect(screen.getByLabelText(data.fields.phone)).toBeDefined();
    expect(screen.getByLabelText(data.fields.postalCode)).toBeDefined();
  });

  it('refuse un e-mail invalide et l’annonce', async () => {
    render(<GuideDownloadDialog data={data} />);
    await open();

    fireEvent.change(screen.getByLabelText(data.fields.email), {
      target: { value: 'pas-un-email' },
    });
    fireEvent.click(screen.getByRole('button', { name: new RegExp(data.submitLabel, 'i') }));

    const alerts = await screen.findAllByRole('alert');
    expect(alerts.some((a) => /adresse e-mail valide/i.test(a.textContent ?? ''))).toBe(true);
    expect(screen.queryByText(data.success.title)).toBeNull();
  });

  it('exige le consentement même avec un e-mail valide', async () => {
    render(<GuideDownloadDialog data={data} />);
    await open();

    fireEvent.change(screen.getByLabelText(data.fields.email), {
      target: { value: 'erick@hellopro.fr' },
    });
    fireEvent.click(screen.getByRole('button', { name: new RegExp(data.submitLabel, 'i') }));

    const alerts = await screen.findAllByRole('alert');
    expect(alerts.some((a) => /informations/i.test(a.textContent ?? ''))).toBe(true);
    expect(screen.queryByText(data.success.title)).toBeNull();
  });

  /**
   * POC : aucune donnée transmise. Ce test échoue si un appel réseau apparaît —
   * signal attendu au moment du branchement réel.
   */
  it('affiche la confirmation sans appel réseau quand tout est valide', async () => {
    const calls: unknown[] = [];
    const originalFetch = globalThis.fetch;
    globalThis.fetch = ((...args: unknown[]) => {
      calls.push(args);
      return Promise.reject(new Error('aucun appel réseau attendu'));
    }) as typeof fetch;

    try {
      render(<GuideDownloadDialog data={data} />);
      await open();

      fireEvent.change(screen.getByLabelText(data.fields.email), {
        target: { value: 'erick@hellopro.fr' },
      });
      fireEvent.click(screen.getByRole('checkbox'));
      fireEvent.click(screen.getByRole('button', { name: new RegExp(data.submitLabel, 'i') }));

      await waitFor(() => expect(screen.getByText(data.success.title)).toBeDefined());
      expect(screen.getByText(/erick@hellopro\.fr/)).toBeDefined();
      expect(calls).toHaveLength(0);
    } finally {
      globalThis.fetch = originalFetch;
    }
  });
});
