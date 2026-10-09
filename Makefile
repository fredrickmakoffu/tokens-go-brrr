.PHONY: test check-version rpm deb packages checksums clean

test:
	python3 -m unittest discover -s tests

check-version:
	python3 scripts/bump_version.py --check

rpm:
	packaging/build.sh rpm

deb:
	packaging/build.sh deb

packages: rpm deb checksums

checksums:
	scripts/make_manifest.py dist

clean:
	rm -rf dist build
