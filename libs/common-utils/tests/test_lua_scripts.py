"""
Tests for Lua script string definitions.
Validates that the scripts are well-formed strings and contain expected Redis commands.
Full integration tests (against a real Redis) will be added in a later task.
"""

from common_utils.concurrency.lua_scripts import (
    ACQUIRE_SCRIPT,
    CORRECT_COUNTERS_SCRIPT,
    RELEASE_SCRIPT,
)


class TestLuaScripts:
    def test_acquire_script_is_non_empty_string(self):
        assert isinstance(ACQUIRE_SCRIPT, str)
        assert len(ACQUIRE_SCRIPT.strip()) > 0

    def test_acquire_script_contains_expected_commands(self):
        assert "redis.call('GET'" in ACQUIRE_SCRIPT
        assert "redis.call('INCR'" in ACQUIRE_SCRIPT
        assert "redis.call('SET'" in ACQUIRE_SCRIPT
        assert "KEYS[1]" in ACQUIRE_SCRIPT
        assert "ARGV[1]" in ACQUIRE_SCRIPT

    def test_release_script_is_non_empty_string(self):
        assert isinstance(RELEASE_SCRIPT, str)
        assert len(RELEASE_SCRIPT.strip()) > 0

    def test_release_script_contains_expected_commands(self):
        assert "redis.call('EXISTS'" in RELEASE_SCRIPT
        assert "redis.call('DEL'" in RELEASE_SCRIPT
        assert "redis.call('DECR'" in RELEASE_SCRIPT
        assert "KEYS[1]" in RELEASE_SCRIPT

    def test_correct_counters_script_is_non_empty_string(self):
        assert isinstance(CORRECT_COUNTERS_SCRIPT, str)
        assert len(CORRECT_COUNTERS_SCRIPT.strip()) > 0

    def test_correct_counters_script_contains_expected_commands(self):
        assert "redis.call('SCAN'" in CORRECT_COUNTERS_SCRIPT
        assert "redis.call('SET'" in CORRECT_COUNTERS_SCRIPT
        assert "KEYS[1]" in CORRECT_COUNTERS_SCRIPT
        assert "ARGV[1]" in CORRECT_COUNTERS_SCRIPT
