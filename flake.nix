{
  description = "StarLang wireless actors, Parrot tool adapters and immutable StarIntel 0.10.1 contracts";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/e5bdc4a41d4c072fe1e3787eaa0320a384741d44";
    star-lang = {
      url = "github:lost-rob0t/star-lang/e9ec1d883627d186aafe0b3647bdc29baea03543";
      flake = false;
    };
    parrot-tools = {
      url = "github:ParrotSec/parrot-tools/a5c278bc04319cf8b0b9e377edd7a46084e63f87";
      flake = false;
    };
  };

  outputs = { self, nixpkgs, star-lang, parrot-tools }:
    let
      systems = [ "x86_64-linux" "aarch64-linux" ];
      eachSystem = nixpkgs.lib.genAttrs systems;
      make = system:
        let
          pkgs = import nixpkgs { inherit system; };
          lib = pkgs.lib;
          python = pkgs.python3.withPackages (ps: [ ps.jsonschema ]);
          lisp = pkgs.sbcl.withPackages (ps: [ ps.bordeaux-threads ]);
          source = lib.cleanSource self;
          catalog = builtins.fromJSON (builtins.readFile ./star_wpa/tool_catalog.json);
          inventory = builtins.fromJSON (builtins.readFile ./catalog/nix-tools.json);
          grGsm = pkgs.callPackage ./nix/providers/gr-gsm.nix { };
          providers = pkgs // {
            starWpa = {
              bluelog = pkgs.callPackage ./nix/providers/bluelog.nix { };
              blueranger = pkgs.callPackage ./nix/providers/blueranger.nix { };
              btscanner = pkgs.callPackage ./nix/providers/btscanner.nix { };
              wifi-honey = pkgs.callPackage ./nix/providers/wifi-honey.nix { };
              bluez-hcidump = pkgs.callPackage ./nix/providers/bluez-hcidump.nix { };
              eapmd5pass = pkgs.callPackage ./nix/providers/eapmd5pass.nix { };
              mfterm = pkgs.callPackage ./nix/providers/mfterm.nix { };
            };
            gnuradioWithWirelessModules = pkgs.gnuradio.override {
              extraPackages = [ pkgs.gnuradioPackages.osmosdr grGsm ];
              extraPythonPackages = [ pkgs.gnuradio.python.pkgs.scipy ];
            };
          };
          # Every catalog entry is deliberate. A bad supported attribute or broken
          # derivation fails evaluation instead of disappearing through tryEval.
          entries = assert inventory.nixpkgsRevision == nixpkgs.rev;
            assert (map (r: r.package) inventory.packages) == (map (r: r.package) catalog.packages);
            map (row:
              let
                value = if row.attribute == null then null
                  else lib.getAttrFromPath (lib.splitString "." row.attribute) providers;
                supported = value != null && lib.meta.availableOn pkgs.stdenv.hostPlatform value;
              in row // {
                available = supported;
                reason = if row.attribute == null then row.reason else
                  if !supported then "Provider does not support ${system}" else "Pinned provider; executable coverage is checked at build time";
                inherit value;
              }
            ) inventory.packages;
          available = builtins.filter (row: row.available) entries;
          coverageRows = map (row: {
            inherit (row) package attribute available reason requiredExecutables;
            limitations = row.limitations or [ ];
          }) entries;
          coverage = pkgs.writeText "star-wpa-nix-tool-coverage.json" (builtins.toJSON coverageRows);
          coreEntries = builtins.filter (row: row.package == "aircrack-ng") available;
          toolPaths = rows: lib.unique (map (row: row.value) rows);
          makeBindings = rows: pkgs.runCommand "star-wpa-nix-tool-bindings.json" {
            nativeBuildInputs = [ python ];
            inputsFile = pkgs.writeText "tool-store-inputs.json" (builtins.toJSON {
              coverage = map (row: if lib.elem row.package (map (r: r.package) rows) then row
                else row // { available = false; reason = if row.available then
                  "Package is outside the selected Nix tool profile" else row.reason; }) coverageRows;
              packages = map (row: {
                inherit (row) package requiredExecutables;
                root = "${lib.getBin row.value}";
                version = row.value.version or "unknown";
              } // lib.optionalAttrs (row ? selectExecutables) {
                inherit (row) selectExecutables;
              } // lib.optionalAttrs (row ? executablePrefix) {
                inherit (row) executablePrefix;
              }) rows;
            });
          } ''
            python3 ${source}/scripts/nix-tool-bindings.py "$inputsFile" "$out"
          '';
          nixBindings = makeBindings available;
          coreBindings = makeBindings coreEntries;
          adapters = pkgs.python3Packages.buildPythonPackage {
            pname = "star-wpa";
            version = "0.2.0";
            src = source;
            pyproject = true;
            build-system = [ pkgs.python3Packages.setuptools ];
            dependencies = [ pkgs.python3Packages.jsonschema ];
            nativeCheckInputs = [ pkgs.bash pkgs.coreutils pkgs.dpkg ];
            doCheck = true;
            checkPhase = ''
              runHook preCheck
              export STAR_WPA_TEST_SHELL=${pkgs.runtimeShell}
              python3 scripts/sync-starintel-schema.py --offline
              python3 scripts/build-tool-actors.py --check --source ${parrot-tools}
              python3 -m unittest discover -s tests -p 'test_*.py' -v
              runHook postCheck
            '';
            meta = { description = "Schema-locked wireless protocol and Parrot tool adapters";
                     license = lib.licenses.agpl3Only; platforms = systems; };
          };
          installedPython = pkgs.python3.withPackages (_: [ adapters ]);
          wrapRuntime = name: rows: bindings: pkgs.symlinkJoin {
            inherit name;
            paths = [ adapters ];
            nativeBuildInputs = [ pkgs.makeWrapper ];
            postBuild = ''
              for command in "$out"/bin/*; do
                wrapProgram "$command" \
                  --prefix PATH : "${lib.makeBinPath (toolPaths rows ++ [ pkgs.coreutils pkgs.bash ])}:${lib.makeSearchPath "sbin" (toolPaths rows)}" \
                  --set STAR_WPA_NIX_TOOL_MANIFEST "${bindings}"
              done
            '';
            meta.mainProgram = "star-wpa";
          };
          runtime = wrapRuntime "star-wpa-runtime" coreEntries coreBindings;
          wirelessRuntime = wrapRuntime "star-wpa-wireless-runtime" available nixBindings;
          makeNative = rows: bindings: pkgs.writeShellApplication {
            name = "star-wpa-native";
            runtimeInputs = [ installedPython lisp pkgs.git pkgs.coreutils ] ++ toolPaths rows;
            text = ''
              export STARLANG_SOURCE=${star-lang}
              export STAR_WPA_PYTHON=${installedPython}/bin/python3
              export STAR_WPA_NIX_TOOL_MANIFEST=${bindings}
              export CL_SOURCE_REGISTRY="${source}//:${star-lang}//"
              exec ${lisp}/bin/sbcl --script ${source}/scripts/run-actor.lisp "$@"
            '';
          };
          native = makeNative coreEntries coreBindings;
          wirelessNative = makeNative available nixBindings;
          toolBundle = pkgs.buildEnv { name = "star-wpa-wireless-tool-bundle";
            paths = toolPaths available;
            pathsToLink = [ "/bin" "/sbin" ]; ignoreCollisions = false;
          };
          runtimeChecks = pkgs.runCommand "star-wpa-packaged-tool-discovery" {
            nativeBuildInputs = [ installedPython ];
          } ''
            export STAR_WPA_NIX_TOOL_MANIFEST=${nixBindings}
            cd "$TMPDIR"
            test -x ${toolBundle}/bin/aircrack-ng
            test -x ${toolBundle}/bin/tshark
            python3 ${source}/scripts/check-nix-runtime.py \
              ${wirelessRuntime} ${nixBindings} ${coverage}
            touch "$out"
          '';
          checks = pkgs.runCommand "star-wpa-native-and-contract-checks" {
            nativeBuildInputs = [ python lisp pkgs.nodejs pkgs.git pkgs.bash pkgs.coreutils pkgs.dpkg ];
          } ''
            cp -r ${source} work
            chmod -R u+w work
            cd work
            export STARLANG_SOURCE=${star-lang}
            export STAR_WPA_PYTHON=${python}/bin/python3
            export STAR_WPA_TEST_SHELL=${pkgs.runtimeShell}
            export XDG_CACHE_HOME="$TMPDIR/asdf-cache"
            export CL_SOURCE_REGISTRY="$PWD//:${star-lang}//"
            python3 scripts/check-runtime-pin.py
            python3 scripts/build-tool-actors.py --check --source ${parrot-tools}
            python3 scripts/build-views.py --check
            node tests/views.js
            python3 scripts/native-tool-proof.py
            python3 scripts/sync.py
            python3 scripts/sync.py --check
            python3 scripts/validate-docs.py
            touch "$out"
          '';
        in { inherit adapters runtime wirelessRuntime native wirelessNative checks runtimeChecks coverage nixBindings;
             tools = toolBundle;
             shell = pkgs.mkShell {
               packages = [ installedPython runtime lisp pkgs.nodejs pkgs.git pkgs.dpkg pkgs.nixfmt ] ++ toolPaths coreEntries;
               STARLANG_SOURCE = star-lang;
               STAR_WPA_PYTHON = "${installedPython}/bin/python3";
               STAR_WPA_NIX_TOOL_MANIFEST = coreBindings;
               shellHook = ''export CL_SOURCE_REGISTRY="$PWD//:${star-lang}//"'';
             };
             wirelessShell = pkgs.mkShell {
               packages = [ installedPython wirelessRuntime lisp pkgs.nodejs pkgs.git pkgs.dpkg ] ++ toolPaths available;
               STARLANG_SOURCE = star-lang;
               STAR_WPA_PYTHON = "${installedPython}/bin/python3";
               STAR_WPA_NIX_TOOL_MANIFEST = nixBindings;
               shellHook = ''export CL_SOURCE_REGISTRY="$PWD//:${star-lang}//"'';
             };
             formatter = pkgs.nixfmt; };
    in {
      packages = eachSystem (system: let p = make system; in {
        default = p.runtime;
        star-wpa = p.runtime;
        adapters = p.adapters;
        wireless = p.wirelessRuntime;
        native = p.native;
        wireless-native = p.wirelessNative;
        wireless-tools = p.tools;
        tool-coverage = p.coverage;
        tool-bindings = p.nixBindings;
      });
      apps = eachSystem (system: let p = make system; in {
        default = { type = "app"; program = "${p.runtime}/bin/star-wpa"; };
        wireless = { type = "app"; program = "${p.wirelessRuntime}/bin/star-wpa"; };
        wireless-native = { type = "app"; program = "${p.wirelessNative}/bin/star-wpa-native"; };
        native = { type = "app"; program = "${p.native}/bin/star-wpa-native"; };
      });
      checks = eachSystem (system: let p = make system; in { adapters = p.adapters; native = p.checks; runtime = p.runtimeChecks; });
      devShells = eachSystem (system: { default = (make system).shell; wireless = (make system).wirelessShell; });
      formatter = eachSystem (system: (make system).formatter);
    };
}
