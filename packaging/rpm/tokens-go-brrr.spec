# Built by packaging/build-rpm.sh. VERSION is passed with --define "ver X.Y.Z".
# The source tree is supplied as Source0 (a tarball with a top-level dir).
Name:           tokens-go-brrr
Version:        %{ver}
Release:        1%{?dist}
Summary:        AI coding usage limits in the GNOME top bar
License:        LicenseRef-Unspecified  # TODO: pick a license and add a LICENSE file
URL:            https://github.com/fredrickmakoffu/cursor-spend-monitor
Source0:        %{name}-%{version}.tar.gz
BuildArch:      noarch

BuildRequires:  python3-devel
BuildRequires:  python3-pip
BuildRequires:  python3-setuptools
BuildRequires:  python3-wheel
Requires:       python3 >= 3.11
Requires:       python3-gobject
Requires:       libnotify
Requires:       gnome-shell

%description
A daemon that tracks usage limits for AI coding tools (Cursor, Claude Code,
OpenCode, Codex, Pi) and a GNOME Shell extension that shows them as a status
dot in the top bar. Log out and back in after installing so GNOME Shell loads
the extension, then run `tokens-go-brrr setup`.

%prep
%autosetup -n %{name}-%{version}

%install
packaging/stage.sh %{buildroot}
# Fonts and their licence are only staged when the source tree has them.
: > extra.files
for d in %{_datadir}/fonts/tokens-go-brrr %{_datadir}/licenses/tokens-go-brrr; do
  [ -d "%{buildroot}$d" ] && echo "$d" >> extra.files
done

%post
fc-cache -f /usr/share/fonts/tokens-go-brrr >/dev/null 2>&1 || :

%files -f extra.files
%{_bindir}/tokens-go-brrr
%{python3_sitelib}/tokens_go_brrr
%{python3_sitelib}/tokens_go_brrr-*.dist-info
%{_datadir}/gnome-shell/extensions/tokens-go-brrr@fredrickmakoffu.github.io
%{_prefix}/lib/systemd/user/tokens-go-brrr.service

%changelog
* Fri Oct 09 2026 Fredrick Makoffu <42011427+fredrickmakoffu@users.noreply.github.com> - %{version}-1
- Packaged build; see the GitHub release notes for changes.
