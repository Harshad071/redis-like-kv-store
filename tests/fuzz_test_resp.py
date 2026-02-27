"""
Issue #6: Fuzz Testing for RESP Parser

Tests the Redis protocol parser with random/malformed input.
Ensures parser doesn't crash on bad data (denial of service protection).
"""

import random
import string
import logging
from typing import Generator, Dict, Any

logger = logging.getLogger(__name__)


class RESPFuzzer:
    """
    Generates random/malformed RESP protocol data to test parser robustness.
    
    RESP Format (Redis Serialization Protocol):
    - Simple String: +OK\r\n
    - Error: -Error\r\n
    - Integer: :1000\r\n
    - Bulk String: $6\r\nfoobar\r\n
    - Array: *2\r\n$3\r\nGET\r\n$3\r\nkey\r\n
    """
    
    @staticmethod
    def random_string(min_len: int = 1, max_len: int = 100) -> str:
        """Generate random string."""
        length = random.randint(min_len, max_len)
        return ''.join(random.choices(string.ascii_letters + string.digits, k=length))
    
    @staticmethod
    def random_bytes(min_len: int = 1, max_len: int = 100) -> bytes:
        """Generate random bytes."""
        length = random.randint(min_len, max_len)
        return bytes([random.randint(0, 255) for _ in range(length)])
    
    @staticmethod
    def valid_bulk_string() -> bytes:
        """Generate valid RESP bulk string."""
        data = RESPFuzzer.random_string(1, 50)
        return f"${len(data)}\r\n{data}\r\n".encode()
    
    @staticmethod
    def valid_array_command() -> bytes:
        """Generate valid RESP array (Redis command)."""
        commands = ["GET", "SET", "DEL", "EXPIRE", "TTL"]
        cmd = random.choice(commands)
        args = [cmd] + [RESPFuzzer.random_string(1, 20) for _ in range(random.randint(0, 3))]
        
        resp = f"*{len(args)}\r\n"
        for arg in args:
            resp += f"${len(arg)}\r\n{arg}\r\n"
        return resp.encode()
    
    @staticmethod
    def fuzz_test_cases() -> Generator[bytes, None, None]:
        """
        Generate various malformed RESP test cases.
        
        Tests:
        1. Valid commands (baseline)
        2. Missing CRLF
        3. Invalid length prefix
        4. Negative length
        5. Length mismatch
        6. Huge length (DoS attempt)
        7. Non-UTF8 bytes
        8. Empty array
        9. Incomplete bulk string
        10. Random bytes
        """
        
        # 1. Valid baseline
        yield RESPFuzzer.valid_array_command()
        
        # 2. Missing CRLF (incomplete)
        yield b"*2\r\n$3\r\nGET"
        
        # 3. Invalid length marker
        yield b"*abc\r\n$3\r\nGET\r\n"
        
        # 4. Negative array length
        yield b"*-5\r\n$3\r\nGET\r\n"
        
        # 5. Length mismatch (says 10 bytes, only provides 5)
        yield b"$10\r\nhello\r\n"
        
        # 6. Huge length (DoS attempt - 1GB)
        yield b"$1000000000\r\nhello\r\n"
        
        # 7. Non-UTF8 invalid bytes in bulk string
        yield b"$3\r\n\xff\xfe\xfd\r\n"
        
        # 8. Empty array
        yield b"*0\r\n"
        
        # 9. Incomplete bulk string (missing trailing CRLF)
        yield b"$5\r\nhello"
        
        # 10. Random bytes
        yield RESPFuzzer.random_bytes(1, 50)
        
        # 11. No protocol markers at all
        yield b"this is just random text"
        
        # 12. Null bytes
        yield b"\x00\x00\x00\x00"
        
        # 13. Mixed valid and invalid
        yield b"*2\r\n$3\r\nGET\r\n$INVALID\r\n"
        
        # 14. Very deep nesting
        yield b"*1000\r\n" + (b"$5\r\nhello\r\n" * 1000)
        
        # 15. CRLF in wrong places
        yield b"*2\r\r\n$3\r\nGET\r\n"


def run_fuzz_tests(parser_func, num_iterations: int = 1000) -> Dict[str, Any]:
    """
    Run fuzz tests against a RESP parser function.
    
    Args:
        parser_func: Function that parses RESP data
        num_iterations: How many random test cases to generate
        
    Returns:
        Statistics on crashes, errors, etc.
    """
    stats = {
        "total_tests": 0,
        "valid_parsed": 0,
        "parse_errors": 0,
        "exceptions_caught": 0,
        "exception_types": {},
        "malformed_input_survived": 0,
    }
    
    fuzzer = RESPFuzzer()
    
    # Run documented fuzz cases
    for test_case in fuzzer.fuzz_test_cases():
        stats["total_tests"] += 1
        try:
            result = parser_func(test_case)
            if result is not None:
                stats["valid_parsed"] += 1
            else:
                stats["parse_errors"] += 1
        except Exception as e:
            stats["exceptions_caught"] += 1
            exc_type = type(e).__name__
            stats["exception_types"][exc_type] = stats["exception_types"].get(exc_type, 0) + 1
            logger.debug(f"Caught exception on fuzz input: {exc_type}: {e}")
    
    # Run random fuzz iterations
    for i in range(num_iterations):
        stats["total_tests"] += 1
        
        # Random strategy
        strategy = random.choice([
            "random_bytes",
            "partial_command",
            "huge_length",
            "invalid_markers",
        ])
        
        if strategy == "random_bytes":
            test_case = fuzzer.random_bytes(1, 500)
        elif strategy == "partial_command":
            test_case = fuzzer.valid_array_command()[:random.randint(1, len(fuzzer.valid_array_command()))]
        elif strategy == "huge_length":
            test_case = f"${random.randint(1_000_000, 10_000_000)}\r\nsmall\r\n".encode()
        else:  # invalid_markers
            test_case = (
                b"*" + str(random.randint(-10, 1000)).encode() + 
                b"\r\n$" + str(random.randint(-10, 1000)).encode() + b"\r\n"
            )
        
        try:
            result = parser_func(test_case)
            if result is not None:
                stats["valid_parsed"] += 1
            stats["malformed_input_survived"] += 1
        except Exception as e:
            stats["exceptions_caught"] += 1
            exc_type = type(e).__name__
            stats["exception_types"][exc_type] = stats["exception_types"].get(exc_type, 0) + 1
    
    return stats


if __name__ == "__main__":
    # Example usage
    print("Fuzz test module loaded. Use run_fuzz_tests(parser_func) to test your RESP parser.")
