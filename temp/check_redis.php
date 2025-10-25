<?php
// check_redis.php

header('Content-Type: text/plain');

if (extension_loaded('redis')) {
    echo "✅ YES, the 'phpredis' extension is installed and enabled.\n\n";
    
    try {
        $redis = new Redis();
        // Replace 'redis' with '127.0.0.1' if you are not using Docker's network DNS.
        $redis->connect(getenv('REDIS_HOST') ?: 'redis', getenv('REDIS_PORT') ?: 6379, 1.0); // 1-second timeout
        echo "✅ SUCCESS, successfully connected to the Redis server.\n";
        $redis->close();
    } catch (Exception $e) {
        echo "❌ ERROR, could not connect to the Redis server. Please check if Redis is running and accessible.\n";
        echo "Error message: " . $e->getMessage() . "\n";
    }

} else {
    echo "❌ NO, the 'phpredis' extension is NOT installed.\n";
    echo "You should proceed with the 'predis/predis' library alternative.\n";
}