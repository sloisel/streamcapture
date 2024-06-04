import io
import sys
import time

import streamcapture


for i in range(10):
    buffer = io.BytesIO()
    stdout_capturer = streamcapture.StreamCapture(sys.stdout, buffer)
    try:
        print('1234')
        time.sleep(1)
        buffer_str = buffer.getvalue().decode().rstrip()
        if buffer_str != '1234':
            raise RuntimeError(f'Test failed. Found: {buffer_str}')
    finally:
        stdout_capturer.close()
        buffer.close()
