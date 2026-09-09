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

TAKE_UPLOAD_BYTES = """
local clock = redis.call('TIME')
local now = tonumber(clock[1]) * 1000 + math.floor(tonumber(clock[2]) / 1000)
local duration = tonumber(ARGV[1])
local limit = tonumber(ARGV[2])
local amount = tonumber(ARGV[3])
local used = tonumber(redis.call('HGET', KEYS[2], 'used') or '0')
local expired = redis.call('ZRANGEBYSCORE', KEYS[1], '-inf', now - duration)
for _, event in ipairs(expired) do
    used = used - tonumber(redis.call('HGET', KEYS[2], event) or '0')
    redis.call('HDEL', KEYS[2], event)
end
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', now - duration)
redis.call('HSET', KEYS[2], 'used', used)
if limit < 1 or amount < 0 or used + amount > limit then
    local oldest = redis.call('ZRANGE', KEYS[1], 0, 0, 'WITHSCORES')
    local wait = duration
    if #oldest > 0 then wait = tonumber(oldest[2]) + duration - now end
    redis.call('PEXPIRE', KEYS[1], duration)
    redis.call('PEXPIRE', KEYS[2], duration)
    return {0, wait}
end
redis.call('ZADD', KEYS[1], now, ARGV[4])
redis.call('HSET', KEYS[2], ARGV[4], amount, 'used', used + amount)
redis.call('PEXPIRE', KEYS[1], duration)
redis.call('PEXPIRE', KEYS[2], duration)
return {1, 0}
"""


class SharedRedisCache(RedisCache):
    def take_rate_slot(self, key, limit, duration):
        digest = hashlib.sha256(key.encode()).hexdigest()
        redis_key = self.make_and_validate_key("auth-window:" + digest)
        client = self._cache.get_client(redis_key, write=True)
        allowed, wait_ms = client.eval(TAKE_RATE_SLOT, 1, redis_key, int(duration * 1000), limit, uuid.uuid4().hex)
        return bool(allowed), wait_ms / 1000

    def take_upload_bytes(self, key, amount, limit, duration):
        digest = hashlib.sha256(key.encode()).hexdigest()
        events = self.make_and_validate_key("upload-events:{" + digest + "}")
        weights = self.make_and_validate_key("upload-bytes:{" + digest + "}")
        client = self._cache.get_client(events, write=True)
        allowed, wait_ms = client.eval(
            TAKE_UPLOAD_BYTES, 2, events, weights, int(duration * 1000), limit, amount, uuid.uuid4().hex
        )
        return bool(allowed), wait_ms / 1000
