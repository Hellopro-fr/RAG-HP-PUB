import { Server, Cpu } from 'lucide-react';

const ReplicaMonitor = ({ replicas }) => {
  const formatBytes = (bytes) => {
    if (!bytes) return '0 MB';
    const mb = bytes / 1024 / 1024;
    return `${mb.toFixed(0)} MB`;
  };

  const formatCpu = (load) => {
    if (!load) return '0%';
    return `${(load * 100).toFixed(1)}%`;
  };

  const getStatusColor = (timestamp) => {
    const age = Date.now() - timestamp;
    if (age < 5000) return 'green';
    if (age < 15000) return 'yellow';
    return 'red';
  };

  const CircularProgress = ({ cpu, ram, totalRam }) => {
    const size = 140;
    const strokeWidth = 12;
    const radius = (size - strokeWidth) / 2;
    const circumference = 2 * Math.PI * radius;

    const cpuPercent = Math.min((cpu || 0) * 100, 100);
    // DYNAMIC: Use totalRam from heartbeat, fallback to 6GB if not provided
    const ramLimit = totalRam || (6 * 1024 * 1024 * 1024);
    const ramPercent = Math.min((ram / ramLimit) * 100, 100);

    const cpuOffset = circumference - (cpuPercent / 100) * circumference;
    const ramOffset = circumference - (ramPercent / 100) * circumference;

    return (
      <svg width={size} height={size} className="transform -rotate-90">
        {/* Background circles */}
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius - 18}
          fill="none"
          stroke="#374151"
          strokeWidth={strokeWidth}
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="#374151"
          strokeWidth={strokeWidth}
        />

        {/* CPU (inner circle) */}
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius - 18}
          fill="none"
          stroke="url(#cpuGradient)"
          strokeWidth={strokeWidth}
          strokeDasharray={circumference}
          strokeDashoffset={cpuOffset}
          strokeLinecap="round"
          className="transition-all duration-500"
        />

        {/* RAM (outer circle) */}
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="url(#ramGradient)"
          strokeWidth={strokeWidth}
          strokeDasharray={circumference}
          strokeDashoffset={ramOffset}
          strokeLinecap="round"
          className="transition-all duration-500"
        />

        {/* Gradients */}
        <defs>
          <linearGradient id="cpuGradient" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#3b82f6" />
            <stop offset="100%" stopColor="#06b6d4" />
          </linearGradient>
          <linearGradient id="ramGradient" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#a855f7" />
            <stop offset="100%" stopColor="#ec4899" />
          </linearGradient>
        </defs>
      </svg>
    );
  };

  const activeReplicas = Object.values(replicas).filter(r => Date.now() - r.timestamp < 30000);

  return (
    <div className="bg-gray-800 rounded-lg p-6 shadow-xl">
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-2xl font-bold text-white flex items-center gap-2">
          <Server className="w-6 h-6 text-blue-400" />
          Crawler Replicas
          <span className="text-sm font-normal text-gray-400 ml-2">
            ({activeReplicas.length} active)
          </span>
        </h2>
      </div>

      {activeReplicas.length === 0 ? (
        <div className="text-center py-12 text-gray-400">
          <Server className="w-16 h-16 mx-auto mb-4 opacity-30" />
          <p>Aucun replica actif</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {activeReplicas.map((replica) => {
            const statusColor = getStatusColor(replica.timestamp);

            return (
              <div
                key={replica.replicaId}
                className="bg-gray-900 rounded-lg p-5 border border-gray-700 hover:border-gray-600 transition-all"
              >
                {/* Header */}
                <div className="flex items-center justify-between mb-4">
                  <div className="flex items-center gap-2">
                    <div className={`w-3 h-3 rounded-full ${statusColor === 'green' ? 'bg-green-500 animate-pulse' :
                      statusColor === 'yellow' ? 'bg-yellow-500' : 'bg-red-500'
                      }`} />
                    <span className="text-white font-semibold text-sm truncate">
                      {replica.replicaId.substring(0, 12)}
                    </span>
                  </div>
                  <Cpu className="w-4 h-4 text-blue-400" />
                </div>

                {/* Circular Progress */}
                <div className="flex flex-col items-center mb-4">
                  <div className="relative">
                    <CircularProgress cpu={replica.cpu} ram={replica.ram} totalRam={replica.totalRam} />
                    <div className="absolute inset-0 flex flex-col items-center justify-center">
                      <div className="text-center">
                        <div className="text-xs text-gray-400">CPU</div>
                        <div className="text-lg font-bold text-cyan-400">{formatCpu(replica.cpu)}</div>
                        <div className="text-xs text-gray-400 mt-1">RAM</div>
                        <div className="text-sm font-semibold text-pink-400">{formatBytes(replica.ram)}</div>
                      </div>
                    </div>
                  </div>
                </div>

                {/* Job Info */}
                {replica.domain && (
                  <div className="mb-3 p-2 bg-gray-800 rounded text-xs">
                    <div className="text-gray-400">Job:</div>
                    <div className="text-white font-mono truncate">{replica.domain}</div>
                  </div>
                )}

                {/* Top Processes */}
                {replica.topProcesses && replica.topProcesses.length > 0 && (
                  <div className="mt-3 pt-3 border-t border-gray-700">
                    <div className="text-xs text-gray-400 mb-2">Top RAM Processes:</div>
                    <div className="space-y-1">
                      {replica.topProcesses.map((proc, idx) => (
                        <div key={idx} className="flex justify-between text-xs">
                          <span className="text-gray-300 truncate flex-1 font-mono">{proc.name}</span>
                          <span className="text-purple-400 ml-2">{formatBytes(proc.ram)}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};

export default ReplicaMonitor;