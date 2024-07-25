import io
import sys

import streamcapture

def test():
    buffer = io.BytesIO()
    with streamcapture.StreamCapture(sys.stdout, buffer) as stdout_capturer:
        sys.stdout.buffer.write("1234\n".encode())

    buffer_str = buffer.getvalue().decode().rstrip()
    if buffer_str != '1234':
        raise RuntimeError(f'Test failed. Found: {buffer_str}')
