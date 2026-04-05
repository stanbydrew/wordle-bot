{
  description = "Nix flake for the wordle Discord bot";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = import nixpkgs {
          inherit system;
        };

        pythonEnv = pkgs.python3.withPackages (ps: with ps; [
          discordpy
          python-dotenv
          tzdata
        ]);

        package = pkgs.python3Packages.buildPythonApplication {
          pname = "wordle-bot";
          version = "0.1.0";
          format = "other";

          src = ./.;
          nativeBuildInputs = [ pkgs.makeWrapper ];

          installPhase = ''
            runHook preInstall

            mkdir -p $out/libexec/wordle-bot $out/bin
            cp -r src $out/libexec/wordle-bot/
            cp .env.example README.md requirements.txt $out/libexec/wordle-bot/

            makeWrapper ${pythonEnv}/bin/python $out/bin/wordle-bot \
              --chdir $out/libexec/wordle-bot \
              --add-flags $out/libexec/wordle-bot/src/bot.py

            runHook postInstall
          '';

          meta = with pkgs.lib; {
            description = "Discord bot for tracking Wordle streaks";
            homepage = "https://github.com/stanbydrew/wordle-bot";
            mainProgram = "wordle-bot";
            platforms = platforms.linux ++ platforms.darwin;
          };
        };
      in {
        packages.default = package;

        checks.default = package;

        apps.default = {
          type = "app";
          program = "${package}/bin/wordle-bot";
          meta = {
            description = "Run the wordle Discord bot";
          };
        };

        devShells.default = pkgs.mkShell {
          packages = [
            pythonEnv
          ];
        };
      });
}
