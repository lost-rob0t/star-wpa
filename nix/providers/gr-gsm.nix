{ lib, stdenv, fetchurl, cmake, pkg-config, gnuradio, libosmocore, cppunit, mpir, gmp, fftwFloat, libsndfile }:

let
  # Take all ABI-sensitive dependencies from the same GNU Radio package scope.
  inherit (gnuradio) python boost logLib;
  inherit (gnuradio.pkgs) mkDerivation osmosdr;
  buildRadio = gnuradio.override {
    extraPackages = [ osmosdr ];
    extraPythonPackages = [ python.pkgs.scipy ];
  };
  debianPackaging = fetchurl {
    url = "https://deb.debian.org/debian/pool/main/g/gr-gsm/gr-gsm_1.0.0~20220727-3.debian.tar.xz";
    hash = "sha256-E5ne/Vw0y3Es0M1knzA4qiIPYcgwUQxD683s9jNiaus=";
  };
in
mkDerivation {
  pname = "gr-gsm";
  version = "1.0.0-unstable-2022-07-27-debian3";

  # Debian's GNU Radio 3.10 / pybind11 port, not the old SWIG-based release.
  # Both archive hashes were measured and matched the Debian -3 .dsc.
  src = fetchurl {
    url = "https://deb.debian.org/debian/pool/main/g/gr-gsm/gr-gsm_1.0.0~20220727.orig.tar.xz";
    hash = "sha256-lo8mLdcJCx1ZUaXHQylsi6BjzHESdmfayxiqS82yIVM=";
  };

  strictDeps = true;
  nativeBuildInputs = [
    cmake
    pkg-config
    python
    python.pkgs.mako
    python.pkgs.docutils
  ];
  buildInputs = [
    boost
    logLib
    libosmocore
    cppunit
    mpir
    gmp
    fftwFloat
    libsndfile
    python.pkgs.numpy
    python.pkgs.pybind11
  ];
  propagatedBuildInputs = [ python.pkgs.scipy ];

  postPatch = ''
    tar -xf ${debianPackaging}
    # Omit Debian's /usr desktop-path patch; apps_data is not installed by this
    # revision. Retain its reproducibility, soname and March 2026 Boost fixes.
    for patchFile in \
      1020-reproducible-build.patch \
      2000-ungit-soname \
      3000-fix-boost-asio-api.patch; do
      patch -p1 < "debian/patches/$patchFile"
    done

    # Nix keeps dependency libraries in separate prefixes. Import their actual
    # CMake targets instead of relying on a distro-wide /usr/lib search path.
    substituteInPlace CMakeLists.txt \
      --replace-fail 'find_package(Gnuradio "3.10" REQUIRED)' \
        'find_package(PkgConfig REQUIRED)
    find_package(Gnuradio "3.10" REQUIRED COMPONENTS blocks fft filter analog digital pdu network)'
    substituteInPlace lib/CMakeLists.txt \
      --replace-fail 'gnuradio-network gnuradio-pdu gnuradio-filter volk' \
        'gnuradio::gnuradio-network gnuradio::gnuradio-pdu gnuradio::gnuradio-filter Volk::volk'

    # The port installs under gnuradio.gsm. Fix remaining old package names and
    # the Qt5 SIP import used unconditionally by gnuradio.gsm's __init__.py.
    substituteInPlace apps/grgsm_trx \
      --replace-fail 'from gsm.trx' 'from gnuradio.gsm.trx' \
      --replace-fail 'from gnuradio.gsm.trx.radio_if_lms import RadioInterfaceLMS as Radio' \
        'raise RuntimeError("LimeSDR TRX is not packaged in this Nix profile; only the UHD driver dependency is provided")' \
      --replace-fail 'Set device driver (default %(default)s)' \
        'Set device driver (default %(default)s; Nix profile supports UHD only)'
    substituteInPlace apps/grgsm_decode \
      --replace-fail 'blocks.byte_t' 'gr.types.byte_t'
    substituteInPlace python/gsm/trx/radio_if.py \
      --replace-fail 'from gnuradio import blocks' 'from gnuradio import blocks, pdu' \
      --replace-fail 'blocks.pdu_to_tagged_stream' 'pdu.pdu_to_tagged_stream' \
      --replace-fail 'blocks.byte_t' 'gr.types.byte_t'
    substituteInPlace python/gsm/receiver/multiarfcns_receiver.py \
      --replace-fail 'import sip' 'from PyQt5 import sip'
    substituteInPlace apps/grgsm_livemon.grc \
      --replace-fail 'grgsm.device.get_default_args' 'gsm.device.get_default_args' \
      --replace-fail 'window.WIN_BLACKMAN_hARRIS' 'window.WIN_BLACKMAN_HARRIS'
    substituteInPlace grc/receiver/gsm_multiarfcns_receiver.block.yml \
      --replace-fail 'import grgsm' 'from gnuradio import gsm' \
      --replace-fail 'grgsm.multiarfcns_receiver' 'gsm.multiarfcns_receiver'
  '';

  cmakeFlags = [
    "-DENABLE_DOXYGEN=OFF"
    "-DPYTHON_EXECUTABLE=${python.interpreter}"
    "-DGR_PYTHON_DIR=${python.sitePackages}"
  ];

  preConfigure = ''
    export HOME="$TMPDIR/home"
    mkdir -p "$HOME"
    export QT_QPA_PLATFORM=offscreen
    # grcc only generates Python; it does not start a flowgraph or probe radios.
    # Its wrapper supplies the osmosdr block definitions as well as Python deps.
    export PATH="${buildRadio}/bin:$PATH"
    export PYTHONPATH="${buildRadio.pythonEnv}/${python.sitePackages}:''${PYTHONPATH:-}"
  '';

  # Debian disables parallel builds and ignores the old suite's known races.
  # Use deterministic generation and explicit import/help checks instead.
  enableParallelBuilding = false;
  doCheck = false;
  dontWrapPythonPrograms = true;
  dontWrapQtApps = true;

  postInstall = ''
    # CMake builds out of tree, so source documentation lives one level up.
    install -Dm644 ../COPYING "$out/share/doc/gr-gsm/COPYING"
    install -Dm644 ../debian/copyright "$out/share/doc/gr-gsm/copyright"
  '';

  doInstallCheck = stdenv.buildPlatform.canExecute stdenv.hostPlatform;
  installCheckPhase = ''
    runHook preInstallCheck
    unset CMAKE_BINARY_DIR
    export PYTHONPATH="$out/${python.sitePackages}:${buildRadio.pythonEnv}/${python.sitePackages}"
    ${python.interpreter} -c 'from gnuradio import gr, gsm; import gnuradio.gsm.gsm_python; import gnuradio.gsm.trx.radio_if_uhd; import osmosdr; assert callable(gsm.version); assert gr.types.byte_t is not None'
    for program in grgsm_decode grgsm_scanner grgsm_trx grgsm_capture grgsm_channelize; do
      # These scripts parse --help before constructing a top block, opening
      # sockets, discovering devices, or reading an input capture.
      "$out/bin/$program" --help > "$program-help.txt"
      grep -qi usage "$program-help.txt"
    done
    # This selected branch fails before Radio(...) or any socket/device setup.
    if "$out/bin/grgsm_trx" --driver=lms > unsupported-lms.txt 2>&1; then
      echo "unsupported LimeSDR driver unexpectedly accepted" >&2
      exit 1
    fi
    grep -q 'LimeSDR TRX is not packaged in this Nix profile' unsupported-lms.txt
    test -x "$out/bin/grgsm_livemon"
    test -x "$out/bin/grgsm_livemon_headless"
    runHook postInstallCheck
  '';

  meta = {
    description = "GNU Radio blocks and tools for GSM signal analysis";
    homepage = "https://osmocom.org/projects/gr-gsm/wiki/Gr-gsm";
    license = [ lib.licenses.gpl3Plus lib.licenses.agpl3Plus ];
    mainProgram = "grgsm_decode";
    platforms = lib.platforms.linux;
  };
}
