%define _buildhost reproducible-builder

Name:       harbour-isocam
Summary:    Viewer for the CRY8024 acoustic camera
Version:    0.1.0
Release:    1
License:    MIT
URL:        https://github.com/JimKnopfIoT/harbour-isocam
Source0:    %{name}-%{version}.tar.bz2
BuildArch:  noarch
Vendor:     harbour-isocam contributors
Packager:   harbour-isocam contributors

Requires:   sailfishsilica-qt5 >= 0.10.9
Requires:   pyotherside-qml-plugin-python3-qt5

%description
Viewer for the Crysound SonoCam Pocket CRY8024 acoustic camera. Browse
measurements (camera photo + acoustic source overlay), the exact calibrated
peak frequency and dB, and an upright dB-scale spectrum-bar graph. Downloads
new measurements from the camera over WiFi. QML/Silica UI, PyOtherSide backend.

%prep
%setup -q -n %{name}-%{version}

%build

%install
mkdir -p %{buildroot}%{_datadir}/%{name}
cp -r qml python %{buildroot}%{_datadir}/%{name}/
mkdir -p %{buildroot}%{_datadir}/applications
install -m 644 %{name}.desktop %{buildroot}%{_datadir}/applications/%{name}.desktop
for s in 86x86 108x108 128x128 172x172; do
    mkdir -p %{buildroot}%{_datadir}/icons/hicolor/$s/apps
    install -m 644 icons/$s/%{name}.png \
        %{buildroot}%{_datadir}/icons/hicolor/$s/apps/%{name}.png
done

%files
%defattr(-,root,root,-)
%{_datadir}/%{name}
%{_datadir}/applications/%{name}.desktop
%{_datadir}/icons/hicolor/*/apps/%{name}.png

%changelog
* Wed Jun 24 2026 harbour-isocam contributors 0.1.0-1
- Initial MVP: measurements viewer, camera sync, calibrated peak + spectrum bars.
