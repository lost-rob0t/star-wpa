{ lib, stdenv, fetchurl, libpcap, openssl }:

stdenv.mkDerivation {
  pname = "eapmd5pass";
  version = "1.5-unstable-2017-08-04";

  # Upstream includes the 2017 capture-parser security fixes at this revision.
  src = fetchurl {
    url = "https://github.com/joswr1ght/eapmd5pass/archive/3d5551fc28931351196883b39de92afe65d27789.tar.gz";
    hash = "sha256-n1Tiw4S3NI/2wNupFyfTVV4kaZf8Te7VdI5oMtUSwWg=";
  };

  strictDeps = true;
  buildInputs = [ libpcap openssl ];
  dontConfigure = true;

  makeFlags = [
    "CC=${stdenv.cc.targetPrefix}cc"
    # The old-style declarations in this upstream predate C23 prototypes.
    "CFLAGS=-O2 -Wall -std=gnu17"
  ];
  # The upstream link target uses utils.o without declaring that dependency.
  enableParallelBuilding = false;

  installPhase = ''
    runHook preInstall
    install -Dm755 eapmd5pass "$out/bin/eapmd5pass"
    install -Dm644 README "$out/share/doc/eapmd5pass/README"
    runHook postInstall
  '';

  doInstallCheck = stdenv.buildPlatform.canExecute stdenv.hostPlatform;
  installCheckPhase = ''
    runHook preInstallCheck
    # -V returns before opening a capture, interface or dictionary.
    "$out/bin/eapmd5pass" -V > version.txt
    grep -Fx "eapmd5pass - 1.5" version.txt
    runHook postInstallCheck
  '';

  meta = {
    description = "Offline EAP-MD5 authentication auditing tool";
    homepage = "https://github.com/joswr1ght/eapmd5pass";
    license = lib.licenses.gpl2Only;
    platforms = lib.platforms.linux;
    mainProgram = "eapmd5pass";
  };
}
