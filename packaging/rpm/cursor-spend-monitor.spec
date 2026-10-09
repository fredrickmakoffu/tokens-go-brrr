# Built by packaging/build-rpm.sh. VERSION is passed with --define "ver X.Y.Z".
# The source tree is supplied as Source0 (a tarball with a top-level dir).
Name:           cursor-spend-monitor
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
OpenCode) and a GNOME Shell extension that shows them as a status dot in the
top bar. Log out and back in after installing so GNOME Shell loads the
extension, then run `cursor-spend-monitor setup`.

%prep
%autosetup -n %{name}-%{version}

%install
packaging/stage.sh %{buildroot}

%post
fc-cache -f /usr/share/fonts/ai-usage >/dev/null 2>&1 || :

%files
%{_bindir}/cursor-spend-monitor
%{python3_sitelib}/cursor_spend_monitor
%{python3_sitelib}/cursor_spend_monitor-*.dist-info
%{_datadir}/gnome-shell/extensions/ai-usage@fredrickmakoffu.github.io
%{_prefix}/lib/systemd/user/cursor-spend-monitor.service
%{_datadir}/fonts/ai-usage
%{_datadir}/licenses/cursor-spend-monitor

%changelog
* Fri Oct 09 2026 Fredrick Makoffu <42011427+fredrickmakoffu@users.noreply.github.com> - %{version}-1
- Packaged build; see the GitHub release notes for changes.
