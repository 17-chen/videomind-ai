"""Apply a file-size resource limit in a fresh process, then exec a media tool.

A dedicated launcher avoids changing the multithreaded Worker's own limits or
using unsafe preexec_fn callbacks. Arguments contain only a numeric limit and
an executable command, never provider credentials.
"""

import os
import resource
import sys


def main() -> None:
    limit = int(sys.argv[1])
    if limit <= 0 or len(sys.argv) < 3:
        raise ValueError('A positive file-size limit and command are required')
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_FSIZE, (limit, limit))
    os.execv(sys.argv[2], sys.argv[2:])


if __name__ == '__main__':
    main()
