import streamcapture, sys, os, io, time

def test():
    buffer = io.BytesIO()
    writer = streamcapture.Writer(buffer,1)
    print("This does not get saved to the log file")
    with streamcapture.StreamCapture(sys.stdout,writer):
        os.write(sys.stdout.fileno(),b"1234\n")
        print("5678")
    print("This also does not get saved to the log file",flush=True)
    time.sleep(5)
    buffer_str = buffer.getvalue().decode()
    assert buffer_str=='1234\n5678\n'
    
