all: doc dist test

.PHONY: all clean test doc dist pypi test

streamcapture.html: streamcapture/__init__.py
	pdoc --html .
	cp -f html/streamcapture/index.html streamcapture.html
	rm -rf html

README.md: streamcapture/__init__.py
	python3 -c 'import streamcapture; print(streamcapture.__doc__)' > README.md

clean:
	rm -rf html streamcapture.egg-info dist build

doc: streamcapture.html README.md

dist/.mark: setup.py streamcapture/__init__.py
	rm -rf dist
	python3 setup.py sdist
	touch dist/.mark

dist: dist/.mark

pypi: all
	twine upload dist/*

test/logfile.txt: test/test1.py streamcapture/__init__.py Makefile
	cd test && ../scripts/python test1.py && diff logfile.txt logfile.gold
	cd test && ../scripts/python test3.repeating.py
	cd test && ../scripts/python test4.fast_open_close.py
	cd test && ../scripts/python test5.multi_capture_to_same_buffer.py
	cd test && ../scripts/python test6.buffer_write.py

test: test/logfile.txt
