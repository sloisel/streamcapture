import io
import sys

import streamcapture

def test():
    for i in range(10000):
        buffer = io.BytesIO()
        with streamcapture.StreamCapture(sys.stdout, buffer, echo=False), streamcapture.StreamCapture(sys.stderr, buffer, echo=False):
            print('1234')
            sys.stderr.write('5678\n')
        print(f'Iteration {i}')
        buffer.close()
