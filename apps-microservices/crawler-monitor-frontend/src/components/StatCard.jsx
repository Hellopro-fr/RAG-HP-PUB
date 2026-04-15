const StatCard = ({ title, value, icon: Icon, color, trend }) => (
  <div className="bg-gray-800 p-4 rounded-lg flex items-center gap-4 shadow-lg hover:bg-gray-750 transition-all">
    <div className={`w-12 h-12 flex items-center justify-center rounded-lg bg-${color}-500/20`}>
      <Icon className={`w-6 h-6 text-${color}-400`} />
    </div>
    <div className="flex-1">
      <p className="text-2xl font-bold text-white">{value}</p>
      <p className="text-sm text-gray-400">{title}</p>
      {trend && (
        <p className={`text-xs mt-1 ${trend > 0 ? 'text-green-400' : 'text-red-400'}`}>
          {trend > 0 ? '↑' : '↓'} {Math.abs(trend)}%
        </p>
      )}
    </div>
  </div>
);

export default StatCard;