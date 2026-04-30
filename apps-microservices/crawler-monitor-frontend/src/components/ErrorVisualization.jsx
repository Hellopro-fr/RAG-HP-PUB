import { useMemo } from 'react';
import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid } from 'recharts';
import { Card } from './ui/card';

const TOP_N = 7;

const ErrorVisualization = ({ errors }) => {
  const data = useMemo(() => {
    const types = {};
    errors.forEach(err => {
      const type = err.split(':')[0] || 'Unknown';
      types[type] = (types[type] || 0) + 1;
    });
    const sorted = Object.entries(types)
      .map(([name, value]) => ({ name, value }))
      .sort((a, b) => b.value - a.value);
    if (sorted.length <= TOP_N + 1) return sorted;
    const top = sorted.slice(0, TOP_N);
    const restCount = sorted.slice(TOP_N).reduce((acc, e) => acc + e.value, 0);
    return [...top, { name: `Autres (${sorted.length - TOP_N})`, value: restCount }];
  }, [errors]);

  if (data.length === 0) return null;

  const chartHeight = Math.max(200, data.length * 32);

  return (
    <Card className="p-4">
      <h3 className="mb-3 text-sm font-semibold uppercase tracking-wider text-ink-3">
        Distribution des Erreurs
      </h3>
      <ResponsiveContainer width="100%" height={chartHeight}>
        <BarChart data={data} layout="vertical" margin={{ top: 5, right: 24, left: 8, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" horizontal={false} />
          <XAxis type="number" stroke="hsl(var(--muted-foreground))" allowDecimals={false} />
          <YAxis
            type="category"
            dataKey="name"
            stroke="hsl(var(--muted-foreground))"
            width={140}
            tick={{ fontSize: 12 }}
          />
          <Tooltip
            cursor={{ fill: 'hsl(var(--muted) / 0.5)' }}
            contentStyle={{
              background: 'hsl(var(--popover))',
              border: '1px solid hsl(var(--border))',
              borderRadius: 6,
              color: 'hsl(var(--popover-foreground))',
            }}
            labelStyle={{ color: 'hsl(var(--foreground))' }}
            itemStyle={{ color: 'hsl(var(--destructive))' }}
          />
          <Bar dataKey="value" fill="hsl(var(--destructive))" radius={[0, 4, 4, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </Card>
  );
};

export default ErrorVisualization;
