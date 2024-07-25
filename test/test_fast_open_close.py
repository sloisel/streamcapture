import io
import sys

import streamcapture

def test():
    for i in range(10000):
        buffer = io.BytesIO()
        with streamcapture.StreamCapture(sys.stdout, buffer, echo=False):
            print('1234')
        print(f'Iteration {i}')
        assert buffer.getvalue().decode()=='1234\n'
        buffer.close()
