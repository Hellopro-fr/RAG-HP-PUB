'use client';

import { useSearchParams } from 'next/navigation';
import { Suspense, useEffect, useState } from 'react';

import { Button, Card, Input } from '@/components/ui';
import { api } from '@/lib/api/client';
import { fr } from '@/lib/i18n/fr';

type Methods = { sso: boolean; password: boolean };

function LoginForm() {
  const params = useSearchParams();
  const [login, setLogin] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState(false);
  const [busy, setBusy] = useState(false);
  // Until the server answers, offer the local form (the only method of an install without
  // account-service).
  const [methods, setMethods] = useState<Methods>({ sso: false, password: true });
  useEffect(() => {
    void api.GET('/api/auth/methods').then(({ data }) => {
      if (data) setMethods(data);
    });
  }, []);
  const next = params.get('next');
  const target = next && next.startsWith('/') && !next.startsWith('//') ? next : '/projects';
  const ssoError = params.get('error');
  return (
    <Card className="mx-auto mt-16 max-w-sm space-y-4 p-6">
      <h1 className="text-lg font-semibold">{fr.login.title}</h1>
      {ssoError && (
        <p className="text-sm text-red-600" role="alert">
          {fr.login.errors[ssoError] ?? fr.errors.generic}
        </p>
      )}
      {methods.sso && (
        <a
          href={`/api/auth/sso/start?next=${encodeURIComponent(target)}`}
          className="flex h-9 w-full items-center justify-center rounded-md bg-slate-900 px-4 text-sm font-medium text-white hover:bg-slate-700"
          data-testid="sso-login"
        >
          {fr.login.sso}
        </a>
      )}
      {methods.password && (
        <form
          className="space-y-3"
          onSubmit={async (e) => {
            e.preventDefault();
            setBusy(true);
            setError(false);
            const { response } = await api.POST('/api/auth/login', { body: { login, password } });
            setBusy(false);
            // Full navigation: the layout (menu, level) is rendered server-side for the new session.
            if (response.ok) window.location.assign(target);
            else setError(true);
          }}
        >
          {methods.sso && <p className="text-xs text-slate-500">{fr.login.local}</p>}
          <Input
            aria-label={fr.login.login}
            placeholder={fr.login.login}
            autoComplete="username"
            value={login}
            onChange={(e) => setLogin(e.target.value)}
          />
          <Input
            aria-label={fr.login.password}
            placeholder={fr.login.password}
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          {error && <p className="text-sm text-red-600">{fr.login.failed}</p>}
          <Button
            type="submit"
            variant={methods.sso ? 'outline' : 'default'}
            className="w-full"
            disabled={busy}
          >
            {fr.login.submit}
          </Button>
        </form>
      )}
    </Card>
  );
}

export default function LoginPage() {
  return (
    <Suspense>
      <LoginForm />
    </Suspense>
  );
}
