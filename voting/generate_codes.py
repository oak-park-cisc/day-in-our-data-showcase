"""Offline. Prints slips for check-in and the value for the BALLOT_CODES secret.

Run this before the event, on a machine that will not commit its output:

    python -m voting.generate_codes --count 60

It prints two things to stdout:
  1. A sheet of slips, one code per line, to cut up and hand to volunteers
     at check-in.
  2. A single comma-joined string to paste into the GitHub Actions secret
     BALLOT_CODES.

The generated list must NEVER be written to a file and must NEVER be
committed. This repository is public; a committed code would let anyone
vote as that attendee.
"""
from __future__ import annotations

import argparse
import secrets

# No I, O, 0, 1 - volunteers read these codes off paper and hand them to
# residents at check-in, and those four characters get misread there.
ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
LENGTH = 10


def generate_codes(n: int, rng: secrets.SystemRandom | None = None) -> list[str]:
    """Generate n unique random ballot codes.

    Uses secrets.SystemRandom (a CSPRNG) rather than the random module,
    since these codes are the only thing standing between a ballot and
    anyone who guesses it.
    """
    rng = rng or secrets.SystemRandom()
    codes: set[str] = set()
    while len(codes) < n:
        codes.add("".join(rng.choice(ALPHABET) for _ in range(LENGTH)))
    return sorted(codes)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate ballot codes for check-in.")
    parser.add_argument("--count", type=int, default=60)
    args = parser.parse_args()
    codes = generate_codes(args.count)
    print("--- slips (one per attendee) ---")
    for c in codes:
        print(f"  {c}")
    print("\n--- BALLOT_CODES secret value (paste into GitHub Actions secrets) ---")
    print(",".join(codes))
    print("\nDo not commit this output.")


if __name__ == "__main__":
    main()
