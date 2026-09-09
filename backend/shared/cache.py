import hashlib
import uuid

from django.core.cache.backends.redis import RedisCache

TAKE_RATE_SLOT = """
local clock = redis.call('TIME')
local now = tonumber(clock[1]) * 1000 + math.floor(tonumber(clock[2]) / 1000)
local duration = tonumber(ARGV[1])
local limit = tonumber(ARGV[2])
if limit < 1 then return {0, duration} end
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', now - duration)
if redis.call('ZCARD', KEYS[1]) >= limit then
    local oldest = redis.call('ZRANGE', KEYS[1], 0, 0, 'WITHSCORES')
    return {0, tonumber(oldest[2]) + duration - now}
end
redis.call('ZADD', KEYS[1], now, ARGV[3])
redis.call('PEXPIRE', KEYS[1], duration)
return {1, 0}
"""


class SharedRedisCache(RedisCache):
    def take_rate_slot(self, key, limit, duration):
        digest = hashlib.sha256(key.encode()).hexdigest()
        redis_key = self.make_and_validate_key("auth-window:" + digest)
        client = self._cache.get_client(redis_key, write=True)
        allowed, wait_ms = client.eval(TAKE_RATE_SLOT, 1, redis_key, int(duration * 1000), limit, uuid.uuid4().hex)
        return bool(allowed), wait_ms / 1000
