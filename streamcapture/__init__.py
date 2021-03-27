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
"""

import os, sys, threading, platform

class StreamCapture:
	def __init__(self,stream,writer,echo=True,monkeypatch=None):
		"""
		The `StreamCapture` constructor. Parameters are:

		* `stream`: The stream to capture (e.g. `sys.stdout`). This stream should be connected to an
		            underlying `fileno()`.
		* `writer`: The stream to write to (e.g. `writer=open('logfile.txt','wb'))`). If applicable, the
		            `writer` stream should be opened in binary mode. This object need not be an actual
		            Python stream; any object that implements functions `writer.write(data)` and 
		            `writer.close()` is suitable here. The only caveat is that `StreamCapture` will
		            call into `writer` from a separate thread, so if `writer.write()` or `writer.close()`
		            have significant side-effects, then one should make use of appropriate locking
		            primitives. This is not necessary for plain-old files obtained from `open(...)`, but
		            if a writer accumulates the outputs in an in-memory list, then one should use
		            appropriate thread-safe locking to interact with this list from the main thread.
		* `echo=True`: If `True`, send data to `StreamCapture.dup_fd` in addition to `StreamCapture.writer()`.
		* `monkeypatch`: If `True`, replaces `stream.write(data)` with `os.write(fd,data)` (more or less).
		               This is necessary on Windows for `stdout` and `stderr`.
		               The default is to enable monkeypatching only
		               when Windows is detected via `platform.system()=='Windows'`.
		"""
		(self.active, self.writer, self.stream, self.echo) = (True,writer,stream,echo)
		(self.pipe_read_fd, self.pipe_write_fd) = os.pipe()
		self.dup_fd = os.dup(stream.fileno())
		os.dup2(self.pipe_write_fd,stream.fileno())
		self.monkeypatch = monkeypatch if monkeypatch is not None else platform.system()=='Windows'
		if self.monkeypatch:
			self.oldwrite = stream.write
			stream.write = lambda z: os.write(stream.fileno(),z.encode() if hasattr(z,'encode') else z)
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
		self.stream.flush()
		if self.monkeypatch:
			self.stream.write = self.oldwrite
		os.dup2(self.dup_fd,self.stream.fileno())
		os.close(self.pipe_write_fd)
	def __enter__(self):
		return self
	def __exit__(self,a,b,c):
		self.close()
