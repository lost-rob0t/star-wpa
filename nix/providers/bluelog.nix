{ lib, stdenv, fetchurl, bluez, hwdata, gawk, gnused }:

stdenv.mkDerivation {
  pname = "bluelog";
  version = "1.1.3-unstable-2017-07-19";

  src = fetchurl {
    url = "https://github.com/MS3FGX/Bluelog/archive/42c915453938d2b92500fd661ea822f9b011806c.tar.gz";
    hash = "sha256-xI1b4H48kWyDxzkUW3HXfDraeU5J3P8mVCvcjuMDrSQ=";
  };

  strictDeps = true;
  dontConfigure = true;
  buildInputs = [ bluez ];
  nativeBuildInputs = [ gawk gnused ];
  makeFlags = [ "CC=${stdenv.cc.targetPrefix}cc" ];
  env.NIX_CFLAGS_COMPILE = "-std=gnu17";
  buildFlags = [ "bluelog" "livelog" ];

  postPatch = ''
    # Preserve optional operator configuration under /etc, but use immutable
    # packaged vendor data rather than an install-time network download.
    substituteInPlace config.h \
      --replace-fail '"/etc/bluelog/oui.txt"' "\"$out/share/bluelog/oui.txt\""
  '';

  installPhase = ''
    runHook preInstall
    install -Dm755 bluelog "$out/bin/bluelog"
    install -Dm644 bluelog.1 "$out/share/man/man1/bluelog.1"
    install -Dm644 bluelog.conf "$out/share/bluelog/bluelog.conf.example"
    mkdir -p "$out/share/bluelog/www" "$out/share/doc/bluelog"
    cp -r www/. "$out/share/bluelog/www/"
    ln -s bluelog.css "$out/share/bluelog/www/style.css"
    cp COPYING README README.LIVE ChangeLog "$out/share/doc/bluelog/"
    mkdir -p "$out/share/doc/bluelog/hwdata"
    cp ${hwdata.src}/COPYING ${hwdata.src}/LICENSE "$out/share/doc/bluelog/hwdata/"
    # Match upstream's libmackerel CSV format using the already pinned hwdata
    # input. Do not run Makefile install or scripts/gen_oui.sh (both download).
    grep '(hex)' ${hwdata.src}/oui.txt \
      | awk '{print $1","$3,$4,$5,$6,$7,$8}' \
      | sed 's/ *$//; /^$/d; s/-/:/g; s/,//g2' \
      > "$out/share/bluelog/oui.txt"
    test -s "$out/share/bluelog/oui.txt"
    runHook postInstall
  '';

  doInstallCheck = stdenv.buildPlatform.canExecute stdenv.hostPlatform;
  installCheckPhase = ''
    runHook preInstallCheck
    # Upstream handles --help and exits before opening HCI or creating files.
    "$out/bin/bluelog" --help > help.txt
    grep -q Bluelog help.txt
    runHook postInstallCheck
  '';

  meta = {
    description = "Bluetooth discovery logger with pinned OUI data";
    homepage = "https://github.com/MS3FGX/Bluelog";
    license = lib.licenses.gpl2Only;
    mainProgram = "bluelog";
    platforms = lib.platforms.linux;
  };
}
