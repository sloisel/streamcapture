import streamcapture, sys, os, time
with streamcapture.StreamCapture(sys.stdout,open('logfile.txt','wb')):
	print('hello ',end='',flush=True)
	time.sleep(1)
	print('world ',end='',flush=True)
	time.sleep(1)
	print(9,flush=True)
	time.sleep(1)
	print('bye.',flush=True)
