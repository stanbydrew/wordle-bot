# wordle-bot

Discord bot for tracking Wordle streaks.

## Nix

This repository now exposes a Nix flake with:

- `packages.default`: buildable bot package
- `apps.default`: runnable app entrypoint
- `devShells.default`: development shell with Python dependencies

### Commands

```bash
nix develop
nix flake check
nix build
nix run
```

`nix run` starts the bot, so it still requires the same environment variables as the plain Python entrypoint.
