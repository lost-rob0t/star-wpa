{ lib, stdenv, fetchurl, autoreconfHook, flex, bison, libnfc, readline, openssl }:

stdenv.mkDerivation {
  pname = "mfterm";
  version = "1.0.7-unstable-2019-01-27";

  src = fetchurl {
    url = "https://github.com/4ZM/mfterm/archive/e13d373cc23c4e0b89f112b5e4e6d21f737d937e.tar.gz";
    hash = "sha256-IxkrRsGpaMNMJs1rgaoC6a1MnPvrpvUoeqAB7U+vGKE=";
  };

  strictDeps = true;
  nativeBuildInputs = [ autoreconfHook flex bison ];
  buildInputs = [ libnfc readline openssl ];

  postPatch = ''
    # Match upstream autogen.sh's --foreign without running that script.
    substituteInPlace configure.ac \
      --replace-fail 'AM_INIT_AUTOMAKE' 'AM_INIT_AUTOMAKE([foreign])'
    # OpenSSL 3 retains the DES API needed for Mifare MAC compatibility, but
    # deprecates it. Keep warnings visible rather than pinning old OpenSSL.
    substituteInPlace Makefile.am --replace-fail ' -Werror' ""
  '';

  postInstall = ''
    install -Dm644 README.md "$out/share/doc/mfterm/README.md"
    install -Dm644 COPYING "$out/share/doc/mfterm/COPYING"
  '';

  doInstallCheck = stdenv.buildPlatform.canExecute stdenv.hostPlatform;
  installCheckPhase = ''
    runHook preInstallCheck
    # Both options exit in parse_cmdline, before readline or NFC access.
    "$out/bin/mfterm" --version > version.txt
    grep -Fx 'mfterm 1.0.7' version.txt
    "$out/bin/mfterm" --help > help.txt
    grep -q 'Usage: mfterm' help.txt
    runHook postInstallCheck
  '';

  meta = {
    description = "Terminal interface for Mifare Classic tags";
    longDescription = ''
      Upstream warns against running mfterm as root or loading untrusted tag,
      dictionary, or specification files. Packaging does not remove these
      parser-safety limitations.
    '';
    homepage = "https://github.com/4ZM/mfterm";
    license = lib.licenses.gpl3Plus;
    mainProgram = "mfterm";
    platforms = lib.platforms.linux;
  };
}
