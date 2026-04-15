from __future__ import annotations

# Maximum entries returned by list_tree.
MAX_TREE_ENTRIES = 100

# Maximum matches returned by search_files.
MAX_SEARCH_MATCHES = 20

# Maximum lines returned by read_file in a single call.
MAX_READ_LINES = 500

# Default lines returned by read_file when max_lines is not specified.
DEFAULT_READ_LINES = 200

# Maximum matches returned by search_file_reverse.
MAX_REVERSE_MATCHES = 20

# Maximum context lines (before/after) for search_file_reverse.
MAX_CONTEXT_LINES = 10

# Default context lines for search_file_reverse.
DEFAULT_CONTEXT_LINES = 3

# Bytes to sample from the start of a file to detect binary content.
BINARY_CHECK_BYTES = 8192

# Files larger than this are rejected by read_file and search_file_reverse.
MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024
MAX_FILE_SIZE_MB = MAX_FILE_SIZE_BYTES // (1024 * 1024)
