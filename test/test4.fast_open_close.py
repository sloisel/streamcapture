import io
import sys

import streamcapture


for i in range(10000):
    buffer = io.BytesIO()
    with streamcapture.StreamCapture(sys.stdout, buffer, echo=False):
        print('1234')
    print(f'Iteration {i}')
    buffer.close()
