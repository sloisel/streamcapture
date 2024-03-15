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
        if buffer.getvalue() != '1234\n'.encode():
            raise RuntimeError(f'Test failed. Found: {buffer.getvalue().decode()}')
    finally:
        stdout_capturer.close()
        buffer.close()
