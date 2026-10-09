{ lib, stdenvNoCC, fetchurl, makeWrapper, bash, bluez, gawk, gnugrep, ncurses }:

let
  kaliPackaging = fetchurl {
    url = "https://http.kali.org/pool/main/b/blueranger/blueranger_0.1-1kali7.debian.tar.xz";
    hash = "sha256-0w9rd3e8pcKsJ2RMH8oSE5CznZbzCvflb3EhtCIS88s=";
  };
in
stdenvNoCC.mkDerivation {
  pname = "blueranger";
  version = "0.1";

  # The upstream site is unavailable; Kali retains the original source and
  # its GPL-2-or-later copyright record in its official source archive.
  src = fetchurl {
    url = "https://http.kali.org/pool/main/b/blueranger/blueranger_0.1.orig.tar.gz";
    hash = "sha256-8M/y8odH6YY1y5HWwQmzzRkMIHoEAHsvP4SDqPmKPbw=";
  };

  nativeBuildInputs = [ makeWrapper bash ];
  dontConfigure = true;
  dontBuild = true;

  prePatch = ''
    tar -xf ${kaliPackaging}
    patch -p1 < debian/patches/update-help-example.patch
  '';
  postPatch = ''
    substituteInPlace blueranger.sh \
      --replace-fail '#!/bin/bash' '#!${bash}/bin/bash' \
      --replace-fail 'while /bin/true' 'while true'
  '';

  doCheck = true;
  checkPhase = ''
    runHook preCheck
    bash -n blueranger.sh
    runHook postCheck
  '';

  installPhase = ''
    runHook preInstall
    install -Dm755 blueranger.sh "$out/bin/blueranger"
    install -Dm644 debian/copyright "$out/share/doc/blueranger/copyright"
    wrapProgram "$out/bin/blueranger" \
      --prefix PATH : ${lib.makeBinPath [ bluez gawk gnugrep ncurses ]}
    runHook postInstall
  '';

  doInstallCheck = stdenvNoCC.buildPlatform.canExecute stdenvNoCC.hostPlatform;
  installCheckPhase = ''
    runHook preInstallCheck
    # One argument enters the usage branch before any HCI command.
    "$out/bin/blueranger" --help > help.txt
    grep -q BlueRanger help.txt
    runHook postInstallCheck
  '';

  meta = {
    description = "Bluetooth device proximity locator using link quality";
    homepage = "https://www.kali.org/tools/blueranger/";
    license = lib.licenses.gpl2Plus;
    mainProgram = "blueranger";
    platforms = lib.platforms.linux;
  };
}
