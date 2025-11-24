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
import io
import os, threading, platform
from types import TracebackType
from typing import Optional, Callable, Union, Type, TextIO


class Writer:
    stream: io.IOBase
    count: int
    increment: int
    lock: threading.Lock
    _write: Callable[[bytes], int]

    def __init__(self, stream: io.IOBase, count: Optional[int] = None, lock_write: bool = False):
        """`Writer` constructor.

        Wrapper of a stream to which bytes may be written. Introduces an optional lock for which write which
        may be enabled through `lock_write`.

        :param stream: The stream to wrap.
        :param count: The starting number of users of this writer.
        :param lock_write: Grab the lock before each write operation.
        """
        (self.stream, self.lock_write) = (stream, lock_write)
        if count is None:
            (self.count, self.increment) = (0, 1)
        else:
            (self.count, self.increment) = (count, 0)
        self.lock = threading.Lock()
        self._write = self.locked_write if lock_write else stream.write  # type: ignore[assignment]

    def write_from(self, data: bytes, cap: 'FDCapture') -> int:
        """Perform a write operation.

        :param data: The bytes to write.
        :param cap: Unused. Remains for legacy purposes.

        :return: The amount of bytes written.
        """
        return self._write(data)

    def writer_open(self) -> None:
        """Register that the writer is used."""
        with self.lock:
            self.count += self.increment

    def close(self) -> None:
        """Closes the writer and the underlying stream

        When one is done using a `Writer`, one calls `Writer.close()`. This acquires `Writer.lock` so it is
        thread-safe. Each time `Writer.close()` is called, `Writer.count` is decremented. When `Writer.count`
        reaches `0`, `stream.close()` is called.
        """
        with self.lock:
            self.count -= 1
            if self.count > 0:
                return
        self.stream.close()

    def locked_write(self, z: bytes) -> int:
        """Perform the write operation in a thread-safe manner.

        :param z: Bytes to write.
        :return: Return the amount of bytes written
        """
        with self.lock:
            written = self.stream.write(z)
        return written


class FDCapture:
    """Redirect all output from a file descriptor and write it to `writer`."""

    active: bool
    writer: Union[io.IOBase, Writer]
    fd: int
    echo: bool
    write: Callable[[bytes], int]

    pipe_read_fd: int
    dup_fd: int
    """Placeholder filedescriptor where the stream originally wrote to."""
    thread: threading.Thread

    def __init__(
            self,
            fd: int,
            writer: Union[io.IOBase, Writer],
            echo: bool,
    ):
        """`FDCapture` constructor.

        :param fd: The filedescriptor to capture.
        :param writer: Any bytes received from `fd` are written to this writer.
        :param echo: Enable to also write bytes received to `fd` as well.
        """
        if hasattr(writer, "writer_open"):
            writer.writer_open()
        (self.active, self.writer, self.fd, self.echo) = (True, writer, fd, echo)
        self.write = (
            (lambda data: self.writer.write_from(data, self))  # type: ignore[union-attr, assignment]
            if hasattr(writer, "write_from")
            else writer.write
        )
        (pipe_read_fd, pipe_write_fd) = os.pipe()
        self.pipe_read_fd = pipe_read_fd
        self.dup_fd = os.dup(fd)
        os.dup2(pipe_write_fd, fd)
        # Critical: Close pipe_write_fd immediately after dup2 to prevent subprocess inheritance
        os.close(pipe_write_fd)
        self.thread = threading.Thread(target=self.printer)
        self.thread.start()

    def printer(self):
        """This is the thread that listens to the pipe output and passes it to the writer stream."""
        try:
            while True:
                data = os.read(self.pipe_read_fd, 100000)
                if not data:
                    # EOF - pipe is closed
                    break
                self.write(data)
                if self.echo:
                    os.write(self.dup_fd, data)
        finally:
            os.close(self.pipe_read_fd)

    def close(self):
        """When you want to "uncapture" a stream, use this method."""
        if not self.active:
            return
        self.active = False

        # Restore original fd - this closes the last reference to the pipe write end
        os.dup2(self.dup_fd, self.fd)
        
        # Wait for the reader thread to receive EOF and finish
        self.thread.join()
        
        os.close(self.dup_fd)

    def __enter__(self):
        return self

    def __exit__(
            self,
            exc_type: Optional[Type[BaseException]],
            exc_val: Optional[BaseException],
            exc_tb: Optional[TracebackType],
    ) -> None:
        self.close()


class StreamCapture:
    """Interface for users to redirect a stream to another `io.IOBase`"""

    fdcapture: FDCapture
    stream: Union[io.IOBase, TextIO]
    monkeypatch: bool
    oldwrite: Optional[Callable[[Union[bytes, str]], None]]

    def __init__(
            self,
            stream_to_redirect: Union[io.IOBase, TextIO],
            writer: io.IOBase,
            echo: bool = True,
            monkeypatch: Optional[bool] = None,
    ) -> None:
        """The `StreamCapture` constructor.

        :param stream_to_redirect: Stream which will be redirected.
        :param writer: The stream will be redirected to this writer. It must derive from io.IOBase.
        :param echo: If the redirected stream should also write any output to the original stream.
        :param monkeypatch: If monkeypatching is necessary. Default is None which will perform
            the monkeypatch in case this is run on Windows. Otherwise, the value of monkeypatch
            is used.
        """
        self.fdcapture = FDCapture(stream_to_redirect.fileno(), writer, echo)
        self.stream = stream_to_redirect
        self.monkeypatch = platform.system() == "Windows" if monkeypatch is None else monkeypatch
        if self.monkeypatch:
            self.oldwrite = stream_to_redirect.write  # type: ignore[assignment]
            stream_to_redirect.write = lambda z: os.write(  # type: ignore[method-assign]
                stream_to_redirect.fileno(), z.encode() if hasattr(z, "encode") else z
            )
        else:
            self.oldwrite = None

    def close(self) -> None:
        """When you want to "uncapture" a stream, use this method."""
        self.stream.flush()
        self.fdcapture.close()
        if self.monkeypatch:
            self.stream.write = self.oldwrite  # type: ignore[assignment,method-assign]

    def __enter__(self):
        """Start the stream redirect as a contextmanager."""
        return self

    def __exit__(
            self,
            exc_type: Optional[Type[BaseException]],
            exc_val: Optional[BaseException],
            exc_tb: Optional[TracebackType],
    ) -> None:
        """Stop the stream redirect as a contextmanager.

        Same as running StreamCapture.close()
        """
        self.close()
