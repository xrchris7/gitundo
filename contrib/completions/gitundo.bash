# bash completion for gitundo
# Install: source this file from your ~/.bashrc, or copy it to
#   /etc/bash_completion.d/gitundo   (Linux)
#   $(brew --prefix)/etc/bash_completion.d/gitundo   (macOS)

_gitundo() {
    local cur prev commands
    COMPREPLY=()
    cur="${COMP_WORDS[COMP_CWORD]}"
    prev="${COMP_WORDS[COMP_CWORD-1]}"

    commands="snap list restore diff tag untag prune status on off autowrap help --version"

    if [[ ${COMP_CWORD} -eq 1 ]]; then
        COMPREPLY=( $(compgen -W "${commands}" -- "${cur}") )
        return 0
    fi

    case "${prev}" in
        -C) COMPREPLY=( $(compgen -d -- "${cur}") ); return 0 ;;
        -n|--limit|-k|--keep) COMPREPLY=( $(compgen -W "1 5 10 20 50 100" -- "${cur}") ); return 0 ;;
        -t|--tag) COMPREPLY=( $(compgen -W "$(gitundo list --tags 2>/dev/null | awk '{print $3}')" -- "${cur}") ); return 0 ;;
        restore|diff|tag|untag)
            COMPREPLY=( $(compgen -W "$(gitundo list 2>/dev/null | awk '{print $1}') latest 0" -- "${cur}") )
            return 0 ;;
    esac

    case "${cur}" in
        -*) COMPREPLY=( $(compgen -W "-h --help --version" -- "${cur}") ); return 0 ;;
    esac

    COMPREPLY=( $(compgen -W "${commands}" -- "${cur}") )
    return 0
}

complete -F _gitundo gitundo
