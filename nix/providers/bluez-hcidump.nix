{ lib, stdenv, fetchurl }:

stdenv.mkDerivation (finalAttrs: {
  pname = "bluez-hcidump";
  version = "2.5";

  # The original standalone hcidump release, including its bundled BlueZ
  # library. Modern bluez's btmon has a different CLI and is not a substitute.
  src = fetchurl {
    url = "https://www.kernel.org/pub/linux/bluetooth/bluez-hcidump-${finalAttrs.version}.tar.xz";
    hash = "sha256-wsr4jEjI/foQV97NejPuVYFiXKwPKNw8+qXz3lmFMys=";
  };

  strictDeps = true;
  configureFlags = [ "--sbindir=${placeholder "out"}/bin" ];
  enableParallelBuilding = true;

  doInstallCheck = stdenv.buildPlatform.canExecute stdenv.hostPlatform;
  installCheckPhase = ''
    runHook preInstallCheck
    # --version exits during option parsing, before opening Bluetooth sockets.
    test "$("$out/bin/hcidump" --version)" = "${finalAttrs.version}"
    runHook postInstallCheck
  '';

  meta = {
    description = "Original BlueZ Bluetooth HCI packet analyzer";
    homepage = "https://www.bluez.org/";
    license = lib.licenses.gpl2Plus;
    platforms = lib.platforms.linux;
    mainProgram = "hcidump";
  };
})
