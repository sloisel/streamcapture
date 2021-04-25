r"""
## streamcapture: capture the outputs of Python streams, such as sys.stdout and sys.stderr

### Author: Sébastien Loisel

# Installation

`pip install streamcapture`

# Example usage

```python
import streamcapture, sys, os
print("This does not get saved to the log file")
with streamcapture.StreamCapture(sys.stdout,open('logfile.txt','wb')):
        os.write(sys.stdout.fileno(),b"Hello, captured world!\n")
        os.system('echo Hello from the shell')
        print("More capturing")
print("This also does not get saved to the log file")
```

After execution, this will create a file `logfile.txt` in the current directory, containing
the relevant captured outputs.

# Documentation

Class `StreamCapture(stream, writer, echo=True, monkeypatch=None)` is able to capture,
at the operating system level, the data being written to the given `stream`.
A typical use is to capture all outputs to `sys.stdout` and `sys.stderr`
and log them to a file. This will even capture the outputs of spawned shell commands.

`StreamCapture` works by essentially using `os.dup2` to send `stream.fileno()` to a `os.pipe()`.
A separate thread is used to listen to that `os.pipe` and send the outputs to the destination
`writer` stream. `StreamCapture` also uses `os.dup` to duplicate the original filedescriptor to be able
to restore it at the end. This duplicated filedescriptor is stored in `StreamCapture.dup_fd`, and
writing to this filedescriptor results in writing to the original file, before it was redirected.
For example, when redirecting `sys.stdout`, one can still write to the terminal by writing directly
to `StreamCapture.dup_fd` with `os.write()`.

On Windows, `sys.stdout` and `sys.stderr` do not take kindly to their `fileno()` being
redirected with `os.dup2`. `StreamCapture` features an optional workaround, enabled by the
`monkeypatch` optional parameter to the constructor. When enabled, the workaround
overwrites `stream.write(...)` by an implementation that sends everything to `os.write(self.fd,...)`.
This workaround is enabled when `monkeypatch=True` and disabled when `monkeypatch=False`.
The default is `monkeypatch=None`, in which case monkeypatching is enabled only when 
`platform.system()=='Windows'`.

When writing to multiple streams and file descriptors, sometimes the order in which the writes
appear can be surprising. For example, when writing to stderr and stdout, these outputs do not
necessarily appear in the order in which they occurred during the program execution, because
of various levels of buffering that occur in Python, the C library or the operating system.

At the Python level, streams can be `flush()`ed to attempt to reduce the delay before a `write()`
has delivered its payload. Furthermore, `os.fsync()` can be used on some, but not all, file descriptors.
However, `os.fsync()` usually causes an exception if it is called on `sys.stdout.fileno()` or on a
`os.pipe()`. In principle, the operating system should promtly flush any buffers when a file descriptor
is `os.close()`d, but there is no guarantee. To complicate matters, although one usually prefers minimal
buffering for outputs that go to the console, Python tries very hard to force some sort of buffering on
text-mode files.

We have tried to prevent most forms of buffering at the Python level and at the operating system levels,
but when multiple file descriptors are used, or at the boundary when a `StreamCapture` starts or stops
capturing the underlying stream, some outputs that go to the console may appear in an unexpected order.

More sophisticated behaviors can be handled by implementing a custom stream-like object.
The `writer` object should implement functions `writer.write(data)`, where `data` is a byte string,
and `writer.close()`.

The `echo` flag can be set at construction time `StreamCapture(...,echo=True)` and defaults to `True`.
In this mode, all captured outputs are sent both to the `writer` and also to `StreamCapture.dup_fd`.
This allows one to send, e.g. `stdout` to a log file while simultaneously printing it to the console,
similar to the `tee` console command in Unix. The `echo` flag can be set to `False` to disable this.

One can call `StreamCapture.close()` to cleanly unwind the captured streams. This is automatically
done if `StreamCapture` is used in a `with` block.

One may also wish to capture a filedescriptor without the overhead of a wrapping Python stream.
To that end, one may use `FDCapture(fd,writer,echo=True)`. The parameter `fd` is an integer filedescriptor
to be captured. `StreamCapture` is a thin wrapper around `FDCapture`, it mainly adds the monkeypatching
capability.

`streamcapture.Writer` is a thin wrapper around an underlying stream, that allows sharing a stream
between multiple threads in a thread-safe manner, guaranteeing that the underlying stream is closed
only when all threads have called `close`. `Writer` objects are constructed by
`streamcapture.Writer(stream,count,lock_write = False)`.

`stream`: is a stream that is being wrapped, e.g. `stream = open('logfile.txt','wb')`

`count`: is the number of times that `Writer.close()` will be called before the writer
is finally closed. This is so that a single stream can be used from multiple threads.

`lock_write`: set this to `True` if you want calls to `stream.write()` to be serialized.
This causes `Writer.write` to acquire `Writer.lock` before calling `stream.write`.
If `lock_write=False` then `Writer.lock` is not acquired. Use this when `stream.write` is
thread-safe. `lock_write=False` is the default.

Example usage:
```python
import sys, streamcapture
writer = streamcapture.Writer(open('logfile.txt','wb'),2)
with streamcapture.StreamCapture(sys.stdout,writer), streamcapture.StreamCapture(sys.stderr,writer):
	print("This goes to stdout and is captured to logfile.txt")
	print("This goes to stderr and is also captured to logfile.txt",file=sys.stderr)
```

In the above example, writer will be closed twice: once from the `StreamCapture(sys.stdout,...)`
object, and once from the `StreamCapture(sys.stderr,...)` object. Correspondingly, the `count` parameter
of the `streamcapture.Writer` was set to `2`, so that the underlying stream is only closed after 2
calls to `writer.close()`.
"""

import os, sys, threading, platform

class Writer:
	def __init__(self,stream,count,lock_write = False):
		"""`Writer` constructor."""
		(self.stream,self.count,self.lock_write) = (stream,count,lock_write)
		self.lock = threading.Lock()
		self.write = self.locked_write if lock_write else stream.write
	def close(self):
		"""When one is done using a `Writer`, one calls `Writer.close()`. This acquires `Writer.lock` so it is
		thread-safe. Each time `Writer.close()` is called, `Writer.count` is decremented. When `Writer.count`
		reaches `0`, `stream.close()` is called."""
		with self.lock:
			self.count -= 1
			if(self.count==0):
				self.stream.close()
	def locked_write(self,z):
		with self.lock:
			self.stream.write(z)

class FDCapture:
	def __init__(self,fd,writer,echo=True):
		"""`FDCapture` constructor."""
		(self.active, self.writer, self.fd, self.echo) = (True,writer,fd,echo)
		(self.pipe_read_fd, self.pipe_write_fd) = os.pipe()
		self.dup_fd = os.dup(fd)
		os.dup2(self.pipe_write_fd,fd)
		self.thread = threading.Thread(target=self.printer)
		self.thread.start()
	def printer(self):
		"""This is the thread that listens to the pipe output and passes it to the writer stream."""
		try:
			while True:
				data = os.read(self.pipe_read_fd,100000)
				if(len(data)==0):
					break
				self.writer.write(data)
				if self.echo:
					os.write(self.dup_fd,data)
		finally:
			self.writer.close()
			os.close(self.dup_fd)
			os.close(self.pipe_read_fd)
	def close(self):
		"""When you want to "uncapture" a stream, use this method."""
		if not self.active:
			return
		self.active = False
		os.dup2(self.dup_fd,self.fd)
		os.close(self.pipe_write_fd)
	def __enter__(self):
		return self
	def __exit__(self,a,b,c):
		self.close()

class StreamCapture:
	def __init__(self,stream,writer,echo=True,monkeypatch=None):
		"""The `StreamCapture` constructor."""
		self.fdcapture = FDCapture(stream.fileno(),writer,echo)
		self.stream = stream
		self.monkeypatch = platform.system()=='Windows' if monkeypatch is None else monkeypatch
		if self.monkeypatch:
			self.oldwrite = stream.write
			stream.write = lambda z: os.write(stream.fileno(),z.encode() if hasattr(z,'encode') else z)
	def close(self):
		"""When you want to "uncapture" a stream, use this method."""
		self.stream.flush()
		self.fdcapture.close()
		if self.monkeypatch:
			self.stream.write = self.oldwrite
	def __enter__(self):
		return self
	def __exit__(self,a,b,c):
		self.close()
