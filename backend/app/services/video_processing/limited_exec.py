"""Apply a file-size resource limit in a fresh process, then exec a media tool.

A dedicated launcher avoids changing the multithreaded Worker's own limits or
using unsafe preexec_fn callbacks. Arguments contain a numeric limit, parent PID
and an executable command, never provider credentials.
"""

import os
import ctypes
import resource
import signal
import sys


def bind_to_parent(expected_pid: int) -> None:
    """On Linux, die with the spawning Worker, including the setup/exec race.

    Set this in the fresh launcher, never in the multithreaded Worker. The
    signal survives exec of the ordinary, unprivileged ffmpeg executable.
    Other POSIX hosts retain file limits but lack this Linux guarantee.
    """
    if sys.platform != 'linux':
        return
    libc = ctypes.CDLL(None, use_errno=True)
    # PR_SET_PDEATHSIG: ask the kernel to kill this process if its parent dies.
    if libc.prctl(1, signal.SIGKILL, 0, 0, 0) != 0:
        raise OSError(ctypes.get_errno(), 'Cannot supervise media process')
    # Parent may have died before prctl; never run an orphaned media command.
    if os.getppid() != expected_pid:
        raise RuntimeError('Media process parent already exited')


def main() -> None:
    if len(sys.argv) < 4:
        raise ValueError('A file-size limit, parent PID and command are required')
    limit = int(sys.argv[1])
    parent_pid = int(sys.argv[2])
    if limit <= 0 or parent_pid <= 0:
        raise ValueError('A positive file-size limit and parent PID are required')
    bind_to_parent(parent_pid)
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_FSIZE, (limit, limit))
    os.execv(sys.argv[3], sys.argv[3:])


if __name__ == '__main__':
    main()
