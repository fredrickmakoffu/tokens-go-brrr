.PHONY: smoke test check-version rpm deb packages checksums clean

test:
	python3 -m unittest discover -s tests

check-version:
	python3 scripts/bump_version.py --check

rpm:
	packaging/build.sh rpm

deb:
	packaging/build.sh deb

smoke:
	packaging/smoke.sh rpm
	packaging/smoke.sh deb

packages: rpm deb smoke checksums

checksums:
	scripts/make_manifest.py dist

clean:
	rm -rf dist build
