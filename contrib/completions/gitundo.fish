# fish completion for gitundo
# Install: copy to ~/.config/fish/completions/gitundo.fish

complete -c gitundo -f

# commands
complete -c gitundo -n '__fish_use_subcommand' -a snap       -d 'Snapshot the current working state'
complete -c gitundo -n '__fish_use_subcommand' -a list       -d 'List checkpoints, newest first'
complete -c gitundo -n '__fish_use_subcommand' -a restore    -d 'Restore the working tree to a checkpoint'
complete -c gitundo -n '__fish_use_subcommand' -a diff       -d 'Show what a checkpoint saved'
complete -c gitundo -n '__fish_use_subcommand' -a tag        -d 'Give a checkpoint a human-readable name'
complete -c gitundo -n '__fish_use_subcommand' -a untag      -d 'Remove a tag from a checkpoint'
complete -c gitundo -n '__fish_use_subcommand' -a prune      -d 'Delete old checkpoints'
complete -c gitundo -n '__fish_use_subcommand' -a status     -d 'Show protection state and recent checkpoints'
complete -c gitundo -n '__fish_use_subcommand' -a on         -d 'Enable the guard for this repository'
complete -c gitundo -n '__fish_use_subcommand' -a off        -d 'Disable the guard for this repository'
complete -c gitundo -n '__fish_use_subcommand' -a autowrap   -d 'Install/remove the destructive-command shell wrapper'

# common options
complete -c gitundo -s h -l help -d 'Show help'
complete -c gitundo -l version -d 'Print version'
complete -c gitundo -s C -d 'Run as if started in DIR' -r -a '(__fish_complete_directories)'

# subcommand options
complete -c gitundo -n '__fish_seen_subcommand_from snap' -s m -d 'Message'
complete -c gitundo -n '__fish_seen_subcommand_from snap' -s t -l tag -d 'Tag the snapshot'
complete -c gitundo -n '__fish_seen_subcommand_from snap' -s f -l force -d 'Snapshot even when nothing changed'
complete -c gitundo -n '__fish_seen_subcommand_from list' -s n -l limit -d 'Show at most N checkpoints'
complete -c gitundo -n '__fish_seen_subcommand_from list' -l tags -d 'Only tagged checkpoints'
complete -c gitundo -n '__fish_seen_subcommand_from restore' -l index -d 'Also reset the index'
complete -c gitundo -n '__fish_seen_subcommand_from restore' -l hard -d 'Overwrite local edits'
complete -c gitundo -n '__fish_seen_subcommand_from restore' -l delete-extraneous -d 'Delete untracked files not in the checkpoint'
complete -c gitundo -n '__fish_seen_subcommand_from prune' -s k -l keep -d 'Keep the N most recent checkpoints'
complete -c gitundo -n '__fish_seen_subcommand_from prune' -l no-tags -d 'Do not protect tagged checkpoints'
complete -c gitundo -n '__fish_seen_subcommand_from autowrap' -l uninstall -d 'Remove the wrapper'
complete -c gitundo -n '__fish_seen_subcommand_from autowrap' -s shell -a 'bash zsh' -d 'Which rc file to edit'
