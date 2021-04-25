import streamcapture, sys, os
print("This does not get saved to the log file")
writer = streamcapture.Writer(open('logfile.txt','wb'),1)
with streamcapture.StreamCapture(sys.stdout,writer):
        os.write(sys.stdout.fileno(),b"Hello, captured world!\n")
        os.system('echo Hello from the shell')
        print("More capturing")
print("This also does not get saved to the log file")
