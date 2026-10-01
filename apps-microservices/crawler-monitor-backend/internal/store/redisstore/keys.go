package redisstore

const (
	JobPrefix            = "crawl_job:"
	RunningCountKey      = "crawl_jobs:running_count"
	MaxGlobalKey         = "crawl_jobs:max_global_crawls"
	FailedCallbacksKey   = "crawl_jobs:failed_callbacks"
	UpdatesChannel       = "crawl_updates"
	HeartbeatChannel     = "crawler:heartbeat"
	CapacityHistoryKey   = "capacity:history:zset"
	ReplicaHistoryPrefix = "replica:history:"
	KnownReplicasKey     = "replica:known"
	JobPerfPrefix        = "job:perf:"
)
