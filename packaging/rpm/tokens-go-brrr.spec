# Built by packaging/build-rpm.sh. VERSION is passed with --define "ver X.Y.Z".
# The source tree is supplied as Source0 (a tarball with a top-level dir).
Name:           tokens-go-brrr
Version:        %{ver}
Release:        1%{?dist}
Summary:        Daemon and CLI for AI coding usage limits
# MIT for the application; Barlow fonts (when packaged) are SIL OFL-1.1.
License:        MIT AND OFL-1.1
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

%description
A local daemon and CLI that track usage limits for AI coding tools (Cursor,
Claude Code, OpenCode, Codex, Pi). Install tokens-go-brrr-gnome or
tokens-go-brrr-plasma for a panel UI; this package alone is daemon, CLI,
notifications, and systemd user unit. Run `tokens-go-brrr setup` after install.

%package gnome
Summary:        GNOME Shell extension for tokens-go-brrr
Requires:       %{name} = %{version}-%{release}
Requires:       gnome-shell

%description gnome
GNOME Shell extension that shows AI coding usage limits as a status dot in the
top bar. Log out and back in after installing so GNOME Shell loads the extension.

%package plasma
Summary:        Plasma plasmoid for tokens-go-brrr
Requires:       %{name} = %{version}-%{release}
Requires:       plasma-workspace

%description plasma
Plasma panel plasmoid that shows AI coding usage limits. Add the widget to a
panel (or system tray) after installing.

%prep
%autosetup -n %{name}-%{version}

%install
packaging/stage.sh %{buildroot} all
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
%{_prefix}/lib/systemd/user/tokens-go-brrr.service
%{_datadir}/tokens-go-brrr/

%files gnome
%{_datadir}/gnome-shell/extensions/tokens-go-brrr@fredrickmakoffu.github.io

%files plasma
%{_datadir}/plasma/plasmoids/org.tokensgobrrr.panel

%changelog
* Mon Oct 12 2026 Fredrick Makoffu <42011427+fredrickmakoffu@users.noreply.github.com> - %{version}-1
- Split daemon / GNOME / Plasma packages; see design/PLASMA_AND_PACKAGING.md.
