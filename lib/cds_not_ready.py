"""Turn a not-yet-published CDS retrieve into exit 75 so the workflow retries."""

from __future__ import annotations

import sys

from lib.release_wait import NOT_READY_EXIT, is_fatal, is_not_ready


def install() -> None:
    try:
        import cdsapi
    except Exception:
        return
    original = cdsapi.Client.retrieve
    if getattr(original, "_release_wait_wrapped", False):
        return

    def raise_classified(exc: Exception) -> None:
        if is_fatal(exc) or not is_not_ready(exc):
            raise exc
        print(f"Release data is not available yet: {exc}", file=sys.stderr)
        raise SystemExit(NOT_READY_EXIT) from exc

    def retrieve(self, name, request, target=None, *args, **kwargs):
        try:
            if target is None:
                result = original(self, name, request, *args, **kwargs)
            else:
                result = original(self, name, request, target, *args, **kwargs)
        except SystemExit:
            raise
        except Exception as exc:
            raise_classified(exc)
            return None
        download = getattr(result, "download", None)
        if callable(download):

            def wrapped_download(*download_args, **download_kwargs):
                try:
                    return download(*download_args, **download_kwargs)
                except SystemExit:
                    raise
                except Exception as exc:
                    raise_classified(exc)

            result.download = wrapped_download
        return result

    retrieve._release_wait_wrapped = True
    cdsapi.Client.retrieve = retrieve
