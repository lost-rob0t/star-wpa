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
          # Explicit mappings for Debian package names differing from nixpkgs attributes.
          aliases = {
            "libfreefare-bin" = "libfreefare";
            "libnfc-bin" = "libnfc";
            "wireless-tools" = "wirelesstools";
            "wpasupplicant" = "wpa_supplicant";
            "gpsd" = "gpsd";
            "rtl-433" = "rtl_433";
            "soapysdr-tools" = "soapysdr";
          };
          # Only exact-name/explicit aliases with successful evaluation enter the bundle.
          entries = map (row:
            let
              name = aliases.${row.package} or row.package;
              attempt = builtins.tryEval (let value = pkgs.${name} or null;
                in if value == null then null else builtins.seq value.drvPath value);
            in { inherit (row) package; attribute = name;
                 available = attempt.success && attempt.value != null;
                 value = if attempt.success then attempt.value else null; }
          ) catalog.packages;
          available = builtins.filter (row: row.available) entries;
          coverage = pkgs.writeText "star-wpa-nix-tool-coverage.json" (builtins.toJSON
            (map (row: { inherit (row) package attribute available; }) entries));
          nixBindings = pkgs.runCommand "star-wpa-nix-tool-bindings.json" {
            nativeBuildInputs = [ python ];
            inputsFile = pkgs.writeText "tool-store-inputs.json" (builtins.toJSON
              (map (row: { inherit (row) package; root = "${row.value}";
                version = row.value.version or "unknown"; }) available));
          } ''
            python3 ${source}/scripts/nix-tool-bindings.py "$inputsFile" "$out"
          '';
          adapters = pkgs.python3Packages.buildPythonApplication {
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
          native = pkgs.writeShellApplication {
            name = "star-wpa-native";
            runtimeInputs = [ python lisp pkgs.git pkgs.coreutils pkgs.dpkg ];
            text = ''
              export STARLANG_SOURCE=${star-lang}
              export STAR_WPA_PYTHON=${python}/bin/python3
              export CL_SOURCE_REGISTRY="${source}//:${star-lang}//"
              exec ${lisp}/bin/sbcl --script ${source}/scripts/run-actor.lisp "$@"
            '';
          };
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
        in { inherit adapters native checks coverage nixBindings;
             tools = pkgs.buildEnv { name = "star-wpa-wireless-tool-bundle";
               paths = lib.unique (map (row: row.value) available);
               pathsToLink = [ "/bin" "/sbin" ]; ignoreCollisions = false; };
             shell = pkgs.mkShell {
               packages = [ python lisp pkgs.nodejs pkgs.git pkgs.dpkg pkgs.nixfmt ];
               STARLANG_SOURCE = star-lang;
               STAR_WPA_PYTHON = "${python}/bin/python3";
               shellHook = ''export CL_SOURCE_REGISTRY="$PWD//:${star-lang}//"'';
             };
             wirelessShell = pkgs.mkShell {
               packages = [ python lisp pkgs.nodejs pkgs.git pkgs.dpkg ] ++ lib.unique (map (row: row.value) available);
               STARLANG_SOURCE = star-lang;
               STAR_WPA_PYTHON = "${python}/bin/python3";
               STAR_WPA_NIX_TOOL_MANIFEST = nixBindings;
               shellHook = ''export CL_SOURCE_REGISTRY="$PWD//:${star-lang}//"'';
             };
             formatter = pkgs.nixfmt; };
    in {
      packages = eachSystem (system: let p = make system; in {
        default = p.adapters;
        star-wpa = p.adapters;
        native = p.native;
        wireless-tools = p.tools;
        tool-coverage = p.coverage;
        tool-bindings = p.nixBindings;
      });
      apps = eachSystem (system: let p = make system; in {
        default = { type = "app"; program = "${p.adapters}/bin/star-wpa"; };
        native = { type = "app"; program = "${p.native}/bin/star-wpa-native"; };
      });
      checks = eachSystem (system: let p = make system; in { adapters = p.adapters; native = p.checks; });
      devShells = eachSystem (system: { default = (make system).shell; wireless = (make system).wirelessShell; });
      formatter = eachSystem (system: (make system).formatter);
    };
}
