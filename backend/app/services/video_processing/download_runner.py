"""Private managed-download entry point, never a public command/API."""

import json
import os
import signal
import sys
from threading import Thread
from time import sleep


def main():
    expected_parent, result_fd = map(int, sys.argv[1:])
    if os.getppid() != expected_parent or os.getpgrp() != os.getpid():
        return 2
    os.set_inheritable(result_fd, False)

    def watch_parent():
        while True:
            if os.getppid() != expected_parent:
                os.killpg(os.getpgrp(), signal.SIGKILL)
            sleep(0.25)

    Thread(target=watch_parent, daemon=True).start()
    from app.core.config import settings
    from app.core.errors import ApiError
    from app.core.i18n import t
    from app.services.video_processing.downloader import download_video
    from app.services.video_processing.errors import VideoProcessingError
    from app.services.video_processing.managed_downloader import (
        DOWNLOAD_SETTINGS, MAX_INPUT_BYTES, encode_result,
    )
    try:
        raw = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
        if len(raw) > MAX_INPUT_BYTES:
            raise ValueError()
        # Tools must not inherit the private protocol as their standard input.
        with open(os.devnull, 'rb') as empty:
            os.dup2(empty.fileno(), 0)
        request = json.loads(raw)
        for name in (*DOWNLOAD_SETTINGS, 'video_storage_dir'):
            setattr(settings, name, request['settings'][name])
        result = download_video(request['url'], request['video_id'])
        encoded = encode_result(result)
    except ApiError as exc:
        encoded = json.dumps({'kind': 'api_error', 'message': exc.message, 'status': exc.status_code}).encode()
    except VideoProcessingError as exc:
        encoded = json.dumps({'kind': 'processing_error', 'message': str(exc)}).encode()
    except Exception:
        encoded = json.dumps({'kind': 'processing_error', 'message': t('video_download_failed')}).encode()
    with os.fdopen(result_fd, 'wb', closefd=False) as output:
        output.write(encoded + b'\n')
        output.flush()
    # Keep the group leader alive until the parent acknowledges the frame by
    # killing the group. The parent-death watcher remains active in this gap.
    while True:
        sleep(1)


if __name__ == '__main__':
    raise SystemExit(main())
