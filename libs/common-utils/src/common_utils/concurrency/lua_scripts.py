"""
Atomic Lua scripts for Redis-based concurrency guard.
All slot operations (acquire/release/correct) run atomically via EVAL/EVALSHA.
"""

ACQUIRE_SCRIPT = """
local total_key = KEYS[1]
local writes_key = KEYS[2]
local tier2_waiters_key = KEYS[3]
local lease_key = KEYS[4]

local tier = tonumber(ARGV[1])
local global_max = tonumber(ARGV[2])
local write_ceiling = tonumber(ARGV[3])
local lease_value = ARGV[4]
local lease_ttl = tonumber(ARGV[5])

local total = tonumber(redis.call('GET', total_key) or '0')
local writes = tonumber(redis.call('GET', writes_key) or '0')

if tier == 1 then
    if total >= global_max then
        return 0
    end
    redis.call('INCR', total_key)
    redis.call('SET', lease_key, lease_value, 'EX', lease_ttl)
    return 1
else
    if writes >= write_ceiling then
        return 0
    end
    if total >= global_max then
        return 0
    end
    if tier == 3 then
        local tier2_waiters = tonumber(redis.call('GET', tier2_waiters_key) or '0')
        if tier2_waiters > 0 then
            return 0
        end
    end
    redis.call('INCR', total_key)
    redis.call('INCR', writes_key)
    redis.call('SET', lease_key, lease_value, 'EX', lease_ttl)
    return 1
end
"""

RELEASE_SCRIPT = """
local total_key = KEYS[1]
local writes_key = KEYS[2]
local lease_key = KEYS[3]

local tier = tonumber(ARGV[1])

if redis.call('EXISTS', lease_key) == 1 then
    redis.call('DEL', lease_key)
    redis.call('DECR', total_key)
    if tonumber(redis.call('GET', total_key) or '0') < 0 then
        redis.call('SET', total_key, '0')
    end
    if tier == 2 or tier == 3 then
        redis.call('DECR', writes_key)
        if tonumber(redis.call('GET', writes_key) or '0') < 0 then
            redis.call('SET', writes_key, '0')
        end
    end
    return 1
end
return 0
"""

CORRECT_COUNTERS_SCRIPT = """
local total_key = KEYS[1]
local writes_key = KEYS[2]
local lease_prefix = ARGV[1]

local cursor = '0'
local total_leases = 0
local write_leases = 0
repeat
    local result = redis.call('SCAN', cursor, 'MATCH', lease_prefix .. '*', 'COUNT', 100)
    cursor = result[1]
    local keys = result[2]
    for _, key in ipairs(keys) do
        total_leases = total_leases + 1
        local value = redis.call('GET', key)
        if value then
            local tier_str = value:match(':(%d+):')
            local tier = tonumber(tier_str)
            if tier == 2 or tier == 3 then
                write_leases = write_leases + 1
            end
        end
    end
until cursor == '0'

local stored_total = tonumber(redis.call('GET', total_key) or '0')
local stored_writes = tonumber(redis.call('GET', writes_key) or '0')
local corrected = 0

if stored_total ~= total_leases then
    redis.call('SET', total_key, tostring(total_leases))
    corrected = 1
end
if stored_writes ~= write_leases then
    redis.call('SET', writes_key, tostring(write_leases))
    corrected = 1
end

return {corrected, total_leases, write_leases, stored_total, stored_writes}
"""
