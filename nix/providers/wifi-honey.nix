{
  lib, stdenvNoCC, fetchurl, makeWrapper, bash, aircrack-ng, screen,
  wirelesstools, coreutils, gnused, gnugrep, gawk, procps, iproute2, kmod, which,
}:

let
  runtimeInputs = [
    aircrack-ng screen wirelesstools coreutils gnused gnugrep gawk
    procps iproute2 kmod which
  ];
in
stdenvNoCC.mkDerivation {
  pname = "wifi-honey";
  version = "1.0";

  src = fetchurl {
    # Kali's published upstream 1.0 source (sha256 verified against its source .dsc).
    # digi.ninja's original tarball endpoint returns HTTP 403 in hosted Nix builds.
    url = "https://http.kali.org/kali/pool/main/w/wifi-honey/wifi-honey_1.0.orig.tar.gz";
    hash = "sha256-b+FuO+OrJNRgOUFmoUFcn3utcfPo69LzXdfzeUqNY+Q=";
  };

  patches = [ ./wifi-honey-runtime.patch ];
  nativeBuildInputs = [ makeWrapper bash ];
  dontConfigure = true;
  dontBuild = true;

  postPatch = ''
    substituteInPlace wifi_honey.sh \
      --replace-fail '#!/usr/bin/env bash' '#!${bash}/bin/bash' \
      --replace-fail '@template@' "$out/share/wifi-honey/wifi_honey_template.rc"
  '';

  doCheck = true;
  checkPhase = ''
    runHook preCheck
    bash -n wifi_honey.sh
    runHook postCheck
  '';

  installPhase = ''
    runHook preInstall
    install -Dm755 wifi_honey.sh "$out/bin/wifi-honey"
    install -Dm644 wifi_honey_template.rc "$out/share/wifi-honey/wifi_honey_template.rc"
    install -Dm644 README "$out/share/doc/wifi-honey/README"
    wrapProgram "$out/bin/wifi-honey" \
      --prefix PATH : "${lib.makeBinPath runtimeInputs}:${lib.makeSearchPath "sbin" runtimeInputs}"
    runHook postInstall
  '';

  doInstallCheck = stdenvNoCC.buildPlatform.canExecute stdenvNoCC.hostPlatform;
  installCheckPhase = ''
    runHook preInstallCheck
    # The packaging patch handles --help before writable state or radio access.
    export XDG_STATE_HOME="$TMPDIR/wifi-honey-help-state"
    "$out/bin/wifi-honey" --help > help.txt
    grep -q 'Usage:' help.txt
    test ! -e "$XDG_STATE_HOME"
    runHook postInstallCheck
  '';

  meta = {
    description = "Screen-based Wi-Fi honeypot setup helper";
    longDescription = ''
      Packages the upstream 1.0 helper with an immutable screen template and
      private writable capture directories under XDG_STATE_HOME. Its original
      radio setup still assumes legacy mon0 through mon4 interface names;
      compatibility with modern airmon-ng interface creation is not established.
    '';
    homepage = "https://digi.ninja/projects/wifi_honey.php";
    # The upstream README specifies the UK port, not the generic 2.0 license.
    license = {
      shortName = "CC-BY-SA-2.0-UK";
      fullName = "Creative Commons Attribution Share Alike 2.0 UK: England & Wales";
      url = "https://creativecommons.org/licenses/by-sa/2.0/uk/";
      free = true;
      redistributable = true;
    };
    mainProgram = "wifi-honey";
    platforms = lib.platforms.linux;
  };
}
