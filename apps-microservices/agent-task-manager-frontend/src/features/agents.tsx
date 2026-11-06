'use client';

// /agents: presence — actor, current task, heartbeat age, lease remaining, activity rate (§10).
// Heartbeats are not events (§3), so presence is refreshed by polling every 5 s.

import { useQuery } from '@tanstack/react-query';
import Link from 'next/link';
import { useEffect, useState } from 'react';

import { Badge, Card } from '@/components/ui';
import { type ActorView, api, keys, unwrap } from '@/lib/api/client';
import { formatRemaining, fr } from '@/lib/i18n/fr';

import { LeaseCountdown } from './board';

function Age({ iso, now }: { iso: string | null | undefined; now: number }) {
  if (!iso) return <span className="text-slate-400">{fr.task.none}</span>;
  return <span>il y a {formatRemaining(now - new Date(iso).getTime())}</span>;
}

export function AgentsTable({ initial }: { initial: ActorView[] }) {
  const { data } = useQuery({
    queryKey: keys.actors,
    queryFn: () => unwrap(api.GET('/api/actors')),
    initialData: initial,
    refetchInterval: 5000,
  });
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);
  return (
    <div className="space-y-3">
      <h1 className="text-xl font-semibold">{fr.agents.title}</h1>
      <Card className="overflow-x-auto p-4">
        <table className="w-full text-left text-sm" data-testid="agents">
          <thead className="text-xs text-slate-500">
            <tr>
              <th>{fr.agents.actor}</th>
              <th>{fr.agents.kind}</th>
              <th>{fr.agents.task}</th>
              <th>{fr.agents.heartbeat}</th>
              <th>{fr.agents.leaseLeft}</th>
              <th>{fr.agents.activity}</th>
            </tr>
          </thead>
          <tbody>
            {data.map((a) => {
              const lease = a.leases[0];
              return (
                <tr key={a.id} className="border-t border-slate-100" data-testid="agent-row" data-actor={a.name}>
                  <td className="py-1.5">
                    <strong>{a.name}</strong> {a.model && <span className="text-xs text-slate-500">{a.model}</span>}
                  </td>
                  <td>
                    <Badge>{a.kind}</Badge>
                  </td>
                  <td>
                    {lease ? (
                      <Link className="hover:underline" href={`/tasks/${lease.task_id}`}>
                        {lease.task_title}
                      </Link>
                    ) : (
                      <span className="text-slate-400">{fr.agents.idle}</span>
                    )}
                  </td>
                  <td>
                    <Age iso={lease?.last_heartbeat_at ?? a.last_seen_at} now={now} />
                  </td>
                  <td>{lease ? <LeaseCountdown expiresAt={lease.expires_at} paused={lease.paused} /> : fr.task.none}</td>
                  <td>{a.reports_last_hour}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </Card>
    </div>
  );
}
