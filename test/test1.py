import streamcapture, sys, os
print("This does not get saved to the log file")
with streamcapture.StreamCapture(sys.stdout,open('logfile.txt','wb')):
        os.write(sys.stdout.fileno(),b"Hello, captured world!\n")
        os.system('echo Hello from the shell')
        print("More capturing")
print("This also does not get saved to the log file")
