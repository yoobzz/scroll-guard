#!/bin/zsh
# Double-click on a Mac: starts the Scroll Guard server (scroll_guard/app).
exec "${0:A:h}/scroll_guard/app/start.command" "$@"
