"""Shared upload transport helpers for Abel Invest dashboard publishing."""

from __future__ import annotations

import uuid


def build_multipart_form_data(
    *,
    fields: dict[str, str],
    files: dict[str, dict[str, object]],
) -> tuple[bytes, str]:
    boundary = f"----abel-invest-{uuid.uuid4().hex}"
    chunks: list[bytes] = []
    for name, value in fields.items():
        chunks.extend(
            [
                f"--{boundary}\r\n".encode("utf-8"),
                f'Content-Disposition: form-data; name="{name}"\r\n'.encode("utf-8"),
                b"Content-Type: text/plain; charset=utf-8\r\n\r\n",
                str(value).encode("utf-8"),
                b"\r\n",
            ]
        )
    for name, file_info in files.items():
        filename = str(file_info.get("filename") or name)
        content_type = str(file_info.get("content_type") or "application/octet-stream")
        content = file_info.get("content") or b""
        if isinstance(content, str):
            content = content.encode("utf-8")
        chunks.extend(
            [
                f"--{boundary}\r\n".encode("utf-8"),
                (
                    f'Content-Disposition: form-data; name="{name}"; '
                    f'filename="{filename}"\r\n'
                ).encode("utf-8"),
                f"Content-Type: {content_type}\r\n\r\n".encode("utf-8"),
                bytes(content),
                b"\r\n",
            ]
        )
    chunks.append(f"--{boundary}--\r\n".encode("utf-8"))
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"
