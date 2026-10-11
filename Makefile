.PHONY: smoke test lint format format-check check-version rpm deb packages checksums clean

test:
	python3 -m unittest discover -s tests

lint:
	ruff check tokens_go_brrr tests scripts

format:
	ruff format tokens_go_brrr tests scripts

format-check:
	ruff format --check tokens_go_brrr tests scripts

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
