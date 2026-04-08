from __future__ import annotations

# Maximum entries (files + directories combined) returned per directory listing.
MAX_LISTED_ENTRIES = 10

# Maximum matching lines returned per search call.
MAX_RESULTS = 10

# Lines captured before and after each matching line as context.
CONTEXT_LINES = 3

# Files larger than this (bytes) are rejected to avoid loading them fully into memory.
MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024
MAX_FILE_SIZE_MB = MAX_FILE_SIZE_BYTES // (1024 * 1024)
