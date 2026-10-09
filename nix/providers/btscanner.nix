{ lib, stdenv, fetchurl, autoreconfHook, pkg-config, perl, bluez, ncurses, libxml2, hwdata }:

let
  debianPackaging = fetchurl {
    url = "https://deb.debian.org/debian/pool/main/b/btscanner/btscanner_2.1-10.debian.tar.xz";
    hash = "sha256-e8mpyt1TcmJb8AAX+yuogKbr+YM7DmgNSKQnXE7p3z4=";
  };
in
stdenv.mkDerivation {
  pname = "btscanner";
  version = "2.1-debian-10";

  src = fetchurl {
    url = "https://deb.debian.org/debian/pool/main/b/btscanner/btscanner_2.1.orig.tar.gz";
    hash = "sha256-L+uPrOz+70H1Tpg5AXze7ACJ8cEwrQlXPBCewyjiEyA=";
  };

  nativeBuildInputs = [ autoreconfHook pkg-config perl ];
  buildInputs = [ bluez ncurses libxml2 ];
  enableParallelBuilding = true;

  prePatch = ''
    # Apply the complete Debian series, including the buffer-overflow fix,
    # pkg-config detection and cross-building fix. Do not run maintainer scripts.
    tar -xf ${debianPackaging}
    while IFS= read -r patchFile; do
      patch -p1 < "debian/patches/$patchFile"
    done < debian/patches/series
  '';
  postPatch = ''
    substituteInPlace btscanner.xml \
      --replace-fail 'file:///etc/btscanner.dtd' "file://$out/etc/btscanner.dtd" \
      --replace-fail '/var/lib/btscanner/oui.txt' "$out/share/btscanner/oui.txt"
  '';

  configureFlags = [
    "--sysconfdir=${placeholder "out"}/etc"
    "--with-cfgfile=${placeholder "out"}/etc/btscanner.xml"
    "--with-cfgdtd=file://${placeholder "out"}/etc/btscanner.dtd"
  ];

  postInstall = ''
    install -Dm644 debian/btscanner.1 "$out/share/man/man1/btscanner.1"
    mkdir -p "$out/share/btscanner" "$out/share/doc/btscanner"
    cp COPYING README USAGE debian/copyright "$out/share/doc/btscanner/"
    mkdir -p "$out/share/doc/btscanner/hwdata"
    cp ${hwdata.src}/COPYING ${hwdata.src}/LICENSE "$out/share/doc/btscanner/hwdata/"
    # The audited generator only converts a local IEEE OUI text file. Use the
    # pinned hwdata source instead of old bundled data or a network update.
    cp ${hwdata.src}/oui.txt oui.txt.in
    perl mk_oui_list.pl
    test -s oui.txt
    install -m644 oui.txt "$out/share/btscanner/oui.txt"
  '';

  doInstallCheck = stdenv.buildPlatform.canExecute stdenv.hostPlatform;
  installCheckPhase = ''
    runHook preInstallCheck
    # main.c handles --help before config, log, socket or adapter operations.
    "$out/bin/btscanner" --help > help.txt 2>&1
    grep -q 'Display help' help.txt
    test -s "$out/share/btscanner/oui.txt"
    runHook postInstallCheck
  '';

  meta = {
    description = "Ncurses Bluetooth device discovery and information tool";
    homepage = "https://salsa.debian.org/pkg-security-team/btscanner";
    license = lib.licenses.gpl2Only;
    mainProgram = "btscanner";
    platforms = lib.platforms.linux;
  };
}
