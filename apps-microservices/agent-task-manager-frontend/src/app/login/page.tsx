'use client';

import { useRouter, useSearchParams } from 'next/navigation';
import { Suspense, useState } from 'react';

import { Button, Card, Input } from '@/components/ui';
import { api } from '@/lib/api/client';
import { fr } from '@/lib/i18n/fr';

function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const [login, setLogin] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState(false);
  const [busy, setBusy] = useState(false);
  const next = params.get('next');
  const target = next && next.startsWith('/') && !next.startsWith('//') ? next : '/projects';
  return (
    <Card className="mx-auto mt-16 max-w-sm space-y-4 p-6">
      <h1 className="text-lg font-semibold">{fr.login.title}</h1>
      <form
        className="space-y-3"
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          setError(false);
          const { response } = await api.POST('/api/auth/login', { body: { login, password } });
          setBusy(false);
          if (response.ok) router.replace(target);
          else setError(true);
        }}
      >
        <Input aria-label={fr.login.login} placeholder={fr.login.login} autoComplete="username" value={login} onChange={(e) => setLogin(e.target.value)} />
        <Input
          aria-label={fr.login.password}
          placeholder={fr.login.password}
          type="password"
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        {error && <p className="text-sm text-red-600">{fr.login.failed}</p>}
        <Button type="submit" className="w-full" disabled={busy}>
          {fr.login.submit}
        </Button>
      </form>
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
