import { useMemo } from 'react';
import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid } from 'recharts';

const TOP_N = 7; // keep top 7 + "Autres" aggregate

const ErrorVisualization = ({ errors, warnings }) => {
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

  // Dynamic height: 32px per row, min 200px
  const chartHeight = Math.max(200, data.length * 32);

  return (
    <div className="bg-gray-800 p-4 rounded-lg">
      <h3 className="text-lg font-semibold text-white mb-4">Distribution des Erreurs</h3>
      <ResponsiveContainer width="100%" height={chartHeight}>
        <BarChart data={data} layout="vertical" margin={{ top: 5, right: 24, left: 8, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#374151" horizontal={false} />
          <XAxis type="number" stroke="#9ca3af" allowDecimals={false} />
          <YAxis type="category" dataKey="name" stroke="#9ca3af" width={140} tick={{ fontSize: 12 }} />
          <Tooltip
            cursor={{ fill: '#1f2937' }}
            contentStyle={{ background: '#111827', border: '1px solid #374151', borderRadius: 6 }}
            labelStyle={{ color: '#f3f4f6' }}
            itemStyle={{ color: '#ef4444' }}
          />
          <Bar dataKey="value" fill="#ef4444" radius={[0, 4, 4, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
};

export default ErrorVisualization;