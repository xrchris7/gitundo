#compdef gitundo
# zsh completion for gitundo
# Install: place in a dir on your $fpath as _gitundo, e.g.
#   mkdir -p ~/.zfunc && cp gitundo.zsh ~/.zfunc/_gitundo
#   echo 'fpath=(~/.zfunc $fpath); autoload -Uz compinit && compinit' >> ~/.zshrc

_gitundo() {
    local -a commands
    commands=(
        'snap:Snapshot the current working state'
        'list:List checkpoints, newest first'
        'restore:Restore the working tree to a checkpoint'
        'diff:Show what a checkpoint saved'
        'tag:Give a checkpoint a human-readable name'
        'untag:Remove a tag from a checkpoint'
        'prune:Delete old checkpoints'
        'status:Show protection state and recent checkpoints'
        'on:Enable the guard for this repository'
        'off:Disable the guard for this repository'
        'autowrap:Install/remove the destructive-command shell wrapper'
        'help:Full command reference'
    )

    if (( CURRENT == 2 )); then
        _describe 'command' commands
        return
    fi

    case $words[2] in
        restore|diff|tag|untag)
            _arguments '1:checkpoint:($(gitundo list 2>/dev/null | awk "{print \$1}") latest 0)' '*:args:_files'
            ;;
        snap)
            _arguments '-m[message]:message:' '-t[tag]:tag:' '-f[force]'
            ;;
        list)
            _arguments '-n[limit]:limit:' '--tags'
            ;;
        prune)
            _arguments '-k[keep]:keep:' '--no-tags'
            ;;
    esac
}

_gitundo "$@"
