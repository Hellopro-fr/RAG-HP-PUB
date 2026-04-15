import { useMemo } from 'react';
import { ResponsiveContainer, PieChart, Pie, Cell, Tooltip } from 'recharts';

const ErrorVisualization = ({ errors, warnings }) => {
  const errorTypes = useMemo(() => {
    const types = {};
    errors.forEach(err => {
      const type = err.split(':')[0] || 'Unknown';
      types[type] = (types[type] || 0) + 1;
    });
    return Object.entries(types).map(([name, value]) => ({ name, value }));
  }, [errors]);

  const COLORS = ['#ef4444', '#f97316', '#f59e0b', '#eab308', '#84cc16'];

  return (
    <div className="bg-gray-800 p-4 rounded-lg">
      <h3 className="text-lg font-semibold text-white mb-4">Distribution des Erreurs</h3>
      <ResponsiveContainer width="100%" height={300}>
        <PieChart>
          <Pie
            data={errorTypes}
            cx="50%"
            cy="50%"
            labelLine={false}
            label={({ name, percent }) => `${name} (${(percent * 100).toFixed(0)}%)`}
            outerRadius={80}
            fill="#8884d8"
            dataKey="value"
          >
            {errorTypes.map((entry, index) => (
              <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
            ))}
          </Pie>
          <Tooltip />
        </PieChart>
      </ResponsiveContainer>
    </div>
  );
};

export default ErrorVisualization;